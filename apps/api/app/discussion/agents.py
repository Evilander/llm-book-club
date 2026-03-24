"""Discussion agents for multi-agent book discussions."""
from __future__ import annotations
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..providers.llm.base import LLMClient, LLMMessage, LLMResponse
from ..retrieval.search import search_chunks, SearchResult
from ..retrieval.filters import build_evidence_block, flag_suspicious_chunks
from ..settings import settings
from .prompts import get_agent_prompt
from .memory_prompts import MemoryContext, get_memory_aware_prompt
from .token_budget import trim_evidence, estimate_tokens
from .metrics import CitationMetrics, build_citation_metrics

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A citation to a text passage."""
    chunk_id: str
    text: str
    char_start: int | None = None
    char_end: int | None = None
    verified: bool = False
    match_type: str | None = None  # "exact", "normalized", "fuzzy", None


@dataclass
class AgentResponse:
    """Response from a discussion agent."""
    content: str
    citations: list[Citation]
    agent_type: str
    citation_metrics: CitationMetrics | None = None
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize text for comparison (NFKC, lowercase, collapse whitespace)."""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# Span alignment
# ---------------------------------------------------------------------------

def compute_span_alignment(chunk_text: str, quote: str) -> tuple[int, int, str] | None:
    """
    Find where *quote* appears inside *chunk_text* and return the character
    offsets relative to the **original** (un-normalised) chunk text.

    Returns:
        (char_start, char_end, match_type) or None if not found.
        match_type is "exact" when the raw quote is found verbatim, or
        "normalized" when it is found after whitespace/unicode normalisation.
    """
    if not chunk_text or not quote:
        return None

    # 1. Try exact (verbatim) substring match first
    idx = chunk_text.find(quote)
    if idx != -1:
        return (idx, idx + len(quote), "exact")

    # 2. Normalised substring search.
    #    Build a mapping from normalised-text positions back to original
    #    positions so we can return original char offsets.
    norm_chunk = normalize_text(chunk_text)
    norm_quote = normalize_text(quote)

    if not norm_quote:
        return None

    idx = norm_chunk.find(norm_quote)
    if idx == -1:
        return None

    # Map normalised offsets back to original offsets.
    orig_start, orig_end = _map_norm_offsets_to_original(
        chunk_text, idx, idx + len(norm_quote),
    )
    if orig_start is not None:
        return (orig_start, orig_end, "normalized")

    return None


def _map_norm_offsets_to_original(
    original: str,
    norm_start: int,
    norm_end: int,
) -> tuple[int | None, int | None]:
    """
    Given start/end offsets into the normalised version of *original*,
    return the corresponding start/end offsets in the original string.

    The normalisation is: NFKC -> lower -> collapse whitespace -> strip.
    We replay the normalisation character-by-character to build the mapping.
    """
    # Step 1: NFKC + lower
    nfkc = unicodedata.normalize("NFKC", original).lower()

    # Map nfkc positions -> original positions.
    # NFKC can change string length, so we need a character map.
    nfkc_to_orig: list[int] = []
    for orig_idx, ch in enumerate(original):
        expanded = unicodedata.normalize("NFKC", ch).lower()
        for _ in expanded:
            nfkc_to_orig.append(orig_idx)

    # Now collapse whitespace in *nfkc* and build collapsed -> nfkc map.
    collapsed_to_nfkc: list[int] = []
    prev_was_space = False
    stripped_leading = False
    for nfkc_idx, ch in enumerate(nfkc):
        is_space = ch in (' ', '\t', '\n', '\r', '\x0b', '\x0c')
        if is_space:
            if not stripped_leading:
                # leading whitespace -- skip
                continue
            if prev_was_space:
                continue  # collapse
            prev_was_space = True
            collapsed_to_nfkc.append(nfkc_idx)
        else:
            stripped_leading = True
            prev_was_space = False
            collapsed_to_nfkc.append(nfkc_idx)

    # Remove trailing whitespace from the map (strip)
    while collapsed_to_nfkc and nfkc[collapsed_to_nfkc[-1]] in (' ', '\t', '\n', '\r'):
        collapsed_to_nfkc.pop()

    if norm_start >= len(collapsed_to_nfkc) or norm_end > len(collapsed_to_nfkc):
        return (None, None)

    nfkc_start = collapsed_to_nfkc[norm_start]
    # norm_end is exclusive; get the nfkc position of the last included char
    nfkc_end_inclusive = collapsed_to_nfkc[norm_end - 1] if norm_end > 0 else nfkc_start
    # Map to original
    orig_start = nfkc_to_orig[nfkc_start] if nfkc_start < len(nfkc_to_orig) else None
    # For the end we want one past the last original char that contributed
    if nfkc_end_inclusive < len(nfkc_to_orig):
        orig_end_char = nfkc_to_orig[nfkc_end_inclusive]
        # Advance past the full original character
        orig_end = orig_end_char + 1
    else:
        orig_end = len(original)

    if orig_start is None:
        return (None, None)

    return (orig_start, orig_end)


# ---------------------------------------------------------------------------
# Structured JSON response parsing (primary path)
# ---------------------------------------------------------------------------

def parse_structured_response(text: str) -> tuple[str, list[dict]] | None:
    """
    Try to parse an LLM response as structured JSON with citations.

    Expected schema::

        {
          "analysis": "Discussion text with [1], [2] markers...",
          "citations": [
            {"marker": 1, "chunk_id": "abc-123", "quote": "exact text..."},
            ...
          ]
        }

    Returns:
        (analysis_text, citations_list) where each citation dict has keys
        ``chunk_id``, ``text`` (renamed from ``quote``), and ``marker``.
        Returns *None* if the text is not valid structured JSON.
    """
    # The model may wrap its JSON in a markdown code fence -- strip it.
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        # Remove closing fence
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    analysis = data.get("analysis")
    if not isinstance(analysis, str):
        return None

    raw_citations = data.get("citations")
    if not isinstance(raw_citations, list):
        # Valid JSON but no citations array -- treat analysis as the content
        return (analysis, [])

    citations: list[dict] = []
    for item in raw_citations:
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunk_id", "")
        quote = item.get("quote", "")
        marker = item.get("marker")
        if chunk_id and quote:
            citations.append({
                "chunk_id": str(chunk_id).strip(),
                "text": str(quote).strip(),
                "marker": marker,
            })

    return (analysis, citations)


# ---------------------------------------------------------------------------
# Legacy regex citation parsing (fallback)
# ---------------------------------------------------------------------------

def parse_citations(text: str) -> tuple[str, list[dict]]:
    """
    Parse citations from agent response using the legacy regex format.
    Format: [cite: chunk_id, "quoted text..."]

    Returns:
        Tuple of (clean_text, citations)
    """
    pattern = r'\[cite:\s*([^,]+),\s*"([^"]+)"\]'
    citations = []

    for match in re.finditer(pattern, text):
        chunk_id = match.group(1).strip()
        quoted_text = match.group(2).strip()
        citations.append({
            "chunk_id": chunk_id,
            "text": quoted_text,
        })

    # Remove citation markers from text for cleaner display
    clean_text = re.sub(pattern, r'"\2"', text)

    return clean_text, citations


def parse_response_auto(text: str) -> tuple[str, list[dict]]:
    """
    Parse an LLM response, trying structured JSON first, then falling back
    to legacy regex citation parsing.

    Returns:
        (clean_text, citations_list)
    """
    structured = parse_structured_response(text)
    if structured is not None:
        return structured

    logger.debug(
        "Structured JSON parse failed; falling back to regex citation parsing."
    )
    return parse_citations(text)


# ---------------------------------------------------------------------------
# Citation verification (with span alignment)
# ---------------------------------------------------------------------------

def verify_citations(
    db: Session,
    citations: list[dict],
    fuzzy_threshold: float = 0.8,
    allowed_chunk_ids: list[str] | set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Verify that citations actually appear in their referenced chunks and
    compute span alignment (char_start / char_end) within the chunk text.

    Each verified citation dict will include:
        chunk_id, text, char_start, char_end, verified, match_type

    Args:
        db: Database session
        citations: List of citation dicts with chunk_id and text
        fuzzy_threshold: Similarity threshold for fuzzy word-overlap matching

    Returns:
        Tuple of (verified_citations, invalid_citations)
    """
    from ..db.models import Chunk

    verified: list[dict] = []
    invalid: list[dict] = []
    allowed_chunk_id_set = (
        {str(chunk_id) for chunk_id in allowed_chunk_ids}
        if allowed_chunk_ids is not None
        else None
    )

    # Batch-fetch all referenced chunks to avoid N+1 queries
    chunk_ids = list({
        c.get("chunk_id", "") for c in citations if c.get("chunk_id")
    })
    chunks_by_id: dict[str, Chunk] = {}
    if chunk_ids:
        found_chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
        chunks_by_id = {str(c.id): c for c in found_chunks}

    for citation in citations:
        chunk_id = str(citation.get("chunk_id", "")).strip()
        quoted_text = str(citation.get("text", "")).strip()

        if not chunk_id or not quoted_text:
            invalid.append({
                **citation,
                "char_start": None,
                "char_end": None,
                "verified": False,
                "match_type": None,
                "reason": "missing chunk_id or text",
            })
            continue

        if allowed_chunk_id_set is not None and chunk_id not in allowed_chunk_id_set:
            invalid.append({
                **citation,
                "char_start": None,
                "char_end": None,
                "verified": False,
                "match_type": None,
                "reason": "chunk outside session slice",
            })
            continue

        chunk = chunks_by_id.get(chunk_id)

        if not chunk:
            invalid.append({
                **citation,
                "char_start": None,
                "char_end": None,
                "verified": False,
                "match_type": None,
                "reason": f"chunk {chunk_id} not found",
            })
            continue

        if not chunk.text:
            invalid.append({
                **citation,
                "char_start": None,
                "char_end": None,
                "verified": False,
                "match_type": None,
                "reason": "chunk has no text",
            })
            continue

        # Attempt span alignment (exact or normalised)
        span = compute_span_alignment(chunk.text, quoted_text)
        if span is not None:
            char_start, char_end, match_type = span
            verified.append({
                **citation,
                "char_start": char_start,
                "char_end": char_end,
                "verified": True,
                "match_type": match_type,
            })
            continue

        # Fuzzy word-overlap fallback (no span alignment possible)
        chunk_text_normalized = normalize_text(chunk.text)
        quote_normalized = normalize_text(quoted_text)
        quote_words = set(quote_normalized.split())
        chunk_words = set(chunk_text_normalized.split())

        if len(quote_words) > 0:
            overlap = len(quote_words & chunk_words) / len(quote_words)
            if overlap >= fuzzy_threshold:
                verified.append({
                    **citation,
                    "char_start": None,
                    "char_end": None,
                    "verified": True,
                    "match_type": "fuzzy",
                    "match_score": overlap,
                })
                continue

        # No match found
        invalid.append({
            **citation,
            "char_start": None,
            "char_end": None,
            "verified": False,
            "match_type": None,
            "reason": "quote not found in chunk",
        })

    return verified, invalid


def parse_and_verify_citations(
    db: Session,
    text: str,
    strict: bool = False,
    allowed_chunk_ids: list[str] | set[str] | None = None,
) -> tuple[str, list[dict], list[dict]]:
    """
    Parse citations from text (structured JSON then regex fallback) and
    verify them against the database.

    Args:
        db: Database session
        text: Agent response text containing citations
        strict: If True, only return verified citations

    Returns:
        Tuple of (clean_text, verified_citations, invalid_citations)
    """
    clean_text, citations = parse_response_auto(text)
    verified, invalid = verify_citations(
        db,
        citations,
        allowed_chunk_ids=allowed_chunk_ids,
    )

    if strict:
        return clean_text, verified, invalid

    all_citations = verified + invalid
    return clean_text, all_citations, invalid


# ---------------------------------------------------------------------------
# Citation repair
# ---------------------------------------------------------------------------

CITATION_REPAIR_PROMPT = """You previously generated a response with citations, but some citations contained quotes that do not appear in the source chunks.

Here is your original response:
---
{original_response}
---

Here are the actual chunk texts you should cite from (chunk_id -> text):
{chunk_texts}

The following citations were INVALID because the quoted text was not found in the chunk:
{invalid_list}

Please regenerate your response with CORRECTED citations. Each quote MUST be an exact substring copied from the chunk text above. Do NOT paraphrase or modify quotes.

Respond with valid JSON:
{{
  "analysis": "Your corrected discussion text with [1], [2] markers...",
  "citations": [
    {{"marker": 1, "chunk_id": "chunk-id", "quote": "exact substring from chunk text"}}
  ]
}}"""


async def attempt_citation_repair(
    llm_client: LLMClient,
    original_response: str,
    chunks: list[dict],
    invalid_citations: list[dict],
) -> str | None:
    """
    If a significant fraction of citations failed verification, call the LLM
    with a repair prompt asking it to correct citations using exact quotes.

    Args:
        llm_client: The LLM client to use for the repair call
        original_response: The original raw LLM response text
        chunks: List of dicts with ``chunk_id`` and ``text`` for the
                retrieved passages that were provided as evidence
        invalid_citations: The list of citations that failed verification

    Returns:
        The corrected response text (raw LLM output), or None if repair
        fails or is not attempted.
    """
    if not invalid_citations or not chunks:
        return None

    # Build chunk text reference
    chunk_texts_str = "\n".join(
        f'[{c["chunk_id"]}]: "{c["text"]}"'
        for c in chunks
    )

    invalid_list_str = "\n".join(
        f'- chunk_id={c.get("chunk_id")}, quote="{c.get("text", "")[:120]}..."'
        for c in invalid_citations
    )

    repair_prompt = CITATION_REPAIR_PROMPT.format(
        original_response=original_response,
        chunk_texts=chunk_texts_str,
        invalid_list=invalid_list_str,
    )

    try:
        repaired = await llm_client.complete(
            [LLMMessage(role="user", content=repair_prompt)],
            temperature=0.3,
            max_tokens=2048,
        )
        return repaired
    except Exception:
        logger.warning("Citation repair LLM call failed.", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

class BaseAgent:
    """Base class for discussion agents."""

    agent_type: str = "base"

    def __init__(
        self,
        llm_client: LLMClient,
        db: Session,
        book_id: str,
        context: str,
        mode: str = "guided",
        memory: MemoryContext | None = None,
        allowed_section_ids: list[str] | None = None,
        allowed_chunk_ids: list[str] | None = None,
    ):
        self.llm = llm_client
        self.db = db
        self.book_id = book_id
        self.context = context
        self.mode = mode
        self.memory = memory
        self.allowed_section_ids = list(allowed_section_ids or [])
        self.allowed_chunk_ids = list(allowed_chunk_ids or [])
        # Store retrieved chunks for potential citation repair
        self._last_retrieved_chunks: list[dict] = []
        # Use memory-aware prompt if memory is available, otherwise standard prompt
        self.system_prompt = get_memory_aware_prompt(
            self.agent_type, mode, context, memory
        )

    def _build_retrieval_context(self, results: list[SearchResult]) -> str:
        """
        Build the retrieval augmentation string from search results and cache
        the chunk data for citation repair.

        Applies ``settings.max_context_tokens`` to trim evidence if the
        combined chunk text would exceed the token budget.
        """
        if not results:
            self._last_retrieved_chunks = []
            return ""

        # Trim evidence to token budget before building the block
        results = trim_evidence(results, settings.max_context_tokens)

        # Convert search results to chunk dicts
        chunk_dicts = [
            {"chunk_id": str(r.chunk_id), "text": r.text}
            for r in results
        ]
        # Flag any suspicious content
        chunk_dicts = flag_suspicious_chunks(chunk_dicts)
        # Store for potential citation repair
        self._last_retrieved_chunks = chunk_dicts
        # Build safe evidence block
        return "\n\n" + build_evidence_block(chunk_dicts)

    async def _verify_and_maybe_repair(
        self,
        raw_response: str,
        clean_text: str,
        citations: list[dict],
    ) -> tuple[str, list[Citation], CitationMetrics | None]:
        """
        Verify parsed citations and attempt repair if >50% are invalid.

        Returns:
            (final_clean_text, final_citation_objects, citation_metrics)
        """
        if not citations:
            return clean_text, [], None

        verified, invalid = verify_citations(
            self.db,
            citations,
            allowed_chunk_ids=self.allowed_chunk_ids or None,
        )

        total = len(verified) + len(invalid)
        invalid_ratio = len(invalid) / total if total > 0 else 0.0

        repair_attempted = False
        repair_succeeded = False
        post_repair_verified_count = 0
        post_repair_invalid_count = 0

        # Attempt repair if >50% invalid and we have retrieved chunks
        if invalid_ratio > 0.5 and self._last_retrieved_chunks:
            repair_attempted = True
            logger.info(
                "Citation verification: %d/%d invalid (%.0f%%). Attempting repair.",
                len(invalid), total, invalid_ratio * 100,
            )
            repaired_text = await attempt_citation_repair(
                self.llm,
                raw_response,
                self._last_retrieved_chunks,
                invalid,
            )
            if repaired_text:
                new_clean, new_citations = parse_response_auto(repaired_text)
                if new_citations:
                    new_verified, new_invalid = verify_citations(
                        self.db,
                        new_citations,
                        allowed_chunk_ids=self.allowed_chunk_ids or None,
                    )
                    new_total = len(new_verified) + len(new_invalid)
                    new_invalid_ratio = (
                        len(new_invalid) / new_total if new_total > 0 else 0.0
                    )
                    post_repair_verified_count = len(new_verified)
                    post_repair_invalid_count = len(new_invalid)
                    # Only accept the repair if it improved things
                    if new_invalid_ratio < invalid_ratio:
                        repair_succeeded = True
                        logger.info(
                            "Repair improved citations: %d/%d invalid -> %d/%d invalid.",
                            len(invalid), total, len(new_invalid), new_total,
                        )
                        verified = new_verified
                        invalid = new_invalid
                        clean_text = new_clean

        # Build Citation objects from verified + invalid
        all_citation_dicts = verified + invalid
        citation_objects = [
            Citation(
                chunk_id=c.get("chunk_id", ""),
                text=c.get("text", ""),
                char_start=c.get("char_start"),
                char_end=c.get("char_end"),
                verified=c.get("verified", False),
                match_type=c.get("match_type"),
            )
            for c in all_citation_dicts
        ]

        # Build metrics
        cit_metrics = build_citation_metrics(
            verified,
            invalid,
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
            post_repair_verified=post_repair_verified_count,
            post_repair_invalid=post_repair_invalid_count,
        )
        cit_metrics.log_summary(self.agent_type)

        return clean_text, citation_objects, cit_metrics

    async def respond(
        self,
        conversation: list[LLMMessage],
        temperature: float = 0.7,
    ) -> AgentResponse:
        """Generate a response to the conversation."""
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            *conversation,
        ]

        llm_response = await self.llm.complete_with_usage(
            messages,
            temperature=temperature,
            max_tokens=settings.max_tokens_per_turn,
        )
        raw_response = llm_response.content
        clean_text, citations = parse_response_auto(raw_response)
        final_text, citation_objects, cit_metrics = await self._verify_and_maybe_repair(
            raw_response, clean_text, citations,
        )

        return AgentResponse(
            content=final_text,
            citations=citation_objects,
            agent_type=self.agent_type,
            citation_metrics=cit_metrics,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
        )

    async def respond_with_retrieval(
        self,
        conversation: list[LLMMessage],
        query: str | None = None,
        temperature: float = 0.7,
    ) -> AgentResponse:
        """Generate a response with additional retrieval for context."""
        additional_context = ""
        if query:
            results = await search_chunks(
                self.db,
                self.book_id,
                query,
                limit=5,
                section_ids=self.allowed_section_ids or None,
            )
            additional_context = self._build_retrieval_context(results)

        enhanced_system = self.system_prompt
        if additional_context:
            enhanced_system += additional_context

        messages = [
            LLMMessage(role="system", content=enhanced_system),
            *conversation,
        ]

        llm_response = await self.llm.complete_with_usage(
            messages,
            temperature=temperature,
            max_tokens=settings.max_tokens_per_turn,
        )
        raw_response = llm_response.content
        clean_text, citations = parse_response_auto(raw_response)
        final_text, citation_objects, cit_metrics = await self._verify_and_maybe_repair(
            raw_response, clean_text, citations,
        )

        return AgentResponse(
            content=final_text,
            citations=citation_objects,
            agent_type=self.agent_type,
            citation_metrics=cit_metrics,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
        )

    @property
    def last_stream_usage(self) -> LLMResponse | None:
        """Token usage from the most recent ``stream_with_retrieval()`` call.

        Delegates to the underlying LLM client's ``last_stream_usage``
        property, which is populated after the stream is fully consumed.
        """
        return getattr(self.llm, "last_stream_usage", None)

    async def stream_with_retrieval(
        self,
        conversation: list[LLMMessage],
        query: str | None = None,
        temperature: float = 0.7,
    ):
        """
        Stream a response with retrieval context.

        Yields raw text chunks during streaming.  The caller is responsible
        for collecting chunks, then using ``parse_response_auto`` and
        ``verify_citations`` on the assembled text (see engine.py).
        The retrieved chunks are cached on this agent instance so that the
        engine can access them for repair if needed via
        ``agent._last_retrieved_chunks``.

        After the stream is fully consumed, ``agent.last_stream_usage``
        will contain token usage data (if the provider reports it).

        Uses ``settings.max_tokens_per_turn`` as the output token limit.
        """
        additional_context = ""
        if query:
            results = await search_chunks(
                self.db,
                self.book_id,
                query,
                limit=5,
                section_ids=self.allowed_section_ids or None,
            )
            additional_context = self._build_retrieval_context(results)

        enhanced_system = self.system_prompt
        if additional_context:
            enhanced_system += additional_context

        messages = [
            LLMMessage(role="system", content=enhanced_system),
            *conversation,
        ]

        async for chunk in self.llm.stream(
            messages,
            temperature=temperature,
            max_tokens=settings.max_tokens_per_turn,
        ):
            if chunk:
                yield chunk


class FacilitatorAgent(BaseAgent):
    """Facilitator agent that guides the discussion."""

    agent_type = "facilitator"

    async def generate_opening_questions(self, phase: str = "warmup") -> AgentResponse:
        """Generate opening discussion questions for a phase."""
        prompt = """Hey! Welcome to this reading session. Take a look at the text we're discussing and kick things off for us.

Give us 2-3 great opening questions that will get a real conversation going. Pick questions that:
- Are genuinely interesting and invite actual exploration
- Connect to specific moments or passages in the text (cite them!)
- Feel natural and conversational, not like homework assignments
- Build on each other so the conversation has somewhere to go

Start with a warm, brief welcome that acknowledges what we're reading, then jump into the questions. If this text is known for being challenging, acknowledge that — make it approachable."""

        return await self.respond([LLMMessage(role="user", content=prompt)])


class CloseReaderAgent(BaseAgent):
    """Close reader agent that provides detailed textual analysis."""

    agent_type = "close_reader"

    async def analyze_passage(self, passage: str) -> AgentResponse:
        """Provide close reading analysis of a specific passage."""
        prompt = f"""Please provide a close reading analysis of this passage:

"{passage}"

Focus on:
- Word choices and their effects
- Patterns or repetitions
- What's surprising or unusual
- How it connects to the larger work

Always cite specific parts of the passage."""

        return await self.respond([LLMMessage(role="user", content=prompt)])


class SkepticAgent(BaseAgent):
    """Skeptic agent that challenges and clarifies."""

    agent_type = "skeptic"

    async def challenge_claim(self, claim: str) -> AgentResponse:
        """Generate a thoughtful challenge to a claim."""
        prompt = f"""Someone made this claim about the text:

"{claim}"

Please offer a thoughtful response that:
- Acknowledges what's valuable in the claim
- Raises a clarifying question or alternative interpretation
- Points to textual evidence that complicates or nuances the claim

Be curious and constructive, not dismissive."""

        return await self.respond([LLMMessage(role="user", content=prompt)])
