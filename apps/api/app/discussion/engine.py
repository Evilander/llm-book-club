"""Discussion engine for managing multi-agent book discussions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator

from sqlalchemy.orm import Session

from ..db import DiscussionSession, Message, MessageRole, DiscussionMode, BookMemory, ReadingUnit
from ..providers.llm.factory import get_llm_client
from ..providers.llm.base import LLMMessage
from ..retrieval.selector import SessionSlice
from ..retrieval.filters import build_evidence_block
from .agents import (
    FacilitatorAgent,
    CloseReaderAgent,
    SkepticAgent,
    AfterDarkGuideAgent,
    AgentResponse,
    Citation,
    parse_response_auto,
)
from ..settings import settings
from .prompts import DISCUSSION_PROMPTS
from .memory_prompts import MemoryContext, build_memory_from_db
from .metrics import TurnMetrics
from .token_budget import truncate_history
from .sentence_splitter import SentenceSplitter
from .analysis_stream import AnalysisStream
from ..services.book_recall import recall_for_turn
from ..services.reading_scope import ReadingScope, session_scope

from contextlib import aclosing
import logging as _logging
import re

_logger = _logging.getLogger(__name__)


# Per-agent voice mapping for TTS.  Each agent gets a distinct voice so
# users can tell them apart in audio mode without visual cues.
AGENT_VOICES: dict[str, str] = {
    "facilitator": "nova",       # Sam: warm, energetic
    "close_reader": "shimmer",   # Ellis: precise, measured
    "skeptic": "echo",           # Kit: dry, questioning
    "after_dark_guide": "fable", # Lens specialist: lush, intimate
}

STYLE_GUIDANCE = {
    "critical_analysis": "Prioritize close reading, counterarguments, and evidence-backed disagreement. Treat unsupported claims as invitations for scrutiny.",
    "fun": "Keep the exchange playful, lively, and welcoming. Use wit, warmth, and curiosity without losing grounding in the text.",
    "socratic": "Lead with layered questions and let the user reason their way toward conclusions instead of rushing to answers.",
    "sexy": "Keep the conversation flirtatious and sensuous in tone while staying tasteful, text-centered, and non-explicit.",
    "cozy": "Make the session feel calm, companionable, and restorative. Favor encouragement, clarity, and emotional warmth.",
}

DESIRE_LENS_GUIDANCE = {
    "woman": "For adult or erotic material, you may notice feminine glamour, chemistry, fashion, confidence, and desire from a sexy woman's point of view. Keep it consensual, non-explicit, and grounded in the text.",
    "gay_man": "For adult or erotic material, you may notice masculine beauty, style, camp, chemistry, and romantic tension from a sexy gay man's point of view. Keep it consensual, non-explicit, and grounded in the text.",
    "trans_woman": "For adult or erotic material, you may notice femininity, transformation, glamour, confidence, and desire from a sexy trans woman's point of view. Keep it affirming, respectful, non-fetishizing, and grounded in the text.",
}

ADULT_INTENSITY_GUIDANCE = {
    "suggestive": "Adult material may be discussed with sensuality, innuendo, chemistry, and erotic charge, but keep the language restrained and non-graphic.",
    "frank": "Adult material may be discussed more candidly and directly, acknowledging erotic intent and sexual tension in plain language, but keep it non-graphic, consensual, and text-grounded.",
}

EROTIC_FOCUS_GUIDANCE = {
    "longing": "Track yearning, withheld touch, almost-confessions, and the slow ache of wanting.",
    "glamour": "Track style, beauty, ritual, self-presentation, and scenes where elegance sharpens desire.",
    "power": "Track dominance, surrender, control, bargaining, status, and shifts in who sets the terms of intimacy.",
    "tenderness": "Track care, softness, vulnerability, reassurance, and the erotic warmth of emotional safety.",
    "transgression": "Track taboo, risk, secrecy, rule-breaking, and the charge created by what should not happen but might.",
}


def _build_agent_context(
    slice_text: str,
    preferences: dict | None,
) -> str:
    if not preferences:
        return slice_text

    style = preferences.get("discussion_style")
    vibes = preferences.get("vibes") or []
    voice_profile = preferences.get("voice_profile")
    reader_goal = preferences.get("reader_goal")
    desire_lens = preferences.get("desire_lens")
    adult_intensity = preferences.get("adult_intensity")
    erotic_focus = preferences.get("erotic_focus")

    lines = ["SESSION PREFERENCES:"]
    if style:
        lines.append(f"- Primary style: {style}")
        guidance = STYLE_GUIDANCE.get(style)
        if guidance:
            lines.append(f"- Style guidance: {guidance}")
    if vibes:
        lines.append(f"- Vibes to preserve: {', '.join(vibes)}")
    if voice_profile:
        lines.append(f"- Voice preference: {voice_profile}")
    if reader_goal:
        lines.append(f"- Reader goal: {reader_goal}")
    if desire_lens:
        lines.append(f"- Desire lens: {desire_lens}")
        guidance = DESIRE_LENS_GUIDANCE.get(desire_lens)
        if guidance:
            lines.append(f"- Desire-lens guidance: {guidance}")
    if adult_intensity:
        lines.append(f"- Adult intensity: {adult_intensity}")
        guidance = ADULT_INTENSITY_GUIDANCE.get(adult_intensity)
        if guidance:
            lines.append(f"- Adult-intensity guidance: {guidance}")
    if erotic_focus:
        lines.append(f"- Erotic focus: {erotic_focus}")
        guidance = EROTIC_FOCUS_GUIDANCE.get(erotic_focus)
        if guidance:
            lines.append(f"- Erotic-focus guidance: {guidance}")

    lines.extend(["", "CURRENT READING SLICE:", slice_text])
    return "\n".join(lines)


@dataclass
class DiscussionTurn:
    """A single turn in the discussion."""
    role: str  # user, facilitator, close_reader, skeptic, after_dark_guide
    content: str
    citations: list[dict]


class DiscussionEngine:
    """
    Engine for managing multi-agent book discussions.

    Coordinates between user, facilitator, close reader, skeptic, and the
    adult-room specialist when active.
    Supports memory-aware discussions when BookMemory is available.
    """

    def __init__(
        self,
        db: Session,
        session: DiscussionSession,
        slice_data: SessionSlice,
        memory: MemoryContext | None = None,
        reading_scope: ReadingScope | None = None,
    ):
        self.db = db
        self.session = session
        self.slice = slice_data
        self.mode = session.mode.value if hasattr(session.mode, 'value') else session.mode

        self.scope = reading_scope or session_scope(db, session)
        # Existing aggregate summaries lack page provenance. Reader thoughts
        # remain available through scoped recall; unpositioned plot summaries
        # are only usable once the reading boundary reaches the book's end.
        if not self.scope.covers_book:
            memory = None
        elif memory is None:
            memory = self._load_memory_context()
        self.memory = memory
        self.preferences = dict(session.preferences_json or {})
        context_text = build_evidence_block(self.scope.initial_evidence)
        agent_context = _build_agent_context(context_text, self.preferences)

        # Detect adult mode from session preferences
        self.is_adult = (
            self.preferences.get("discussion_style") == "sexy"
            or self.preferences.get("experience_mode") == "after_dark"
            or self.preferences.get("desire_lens") is not None
            or self.preferences.get("adult_intensity") is not None
        )

        # Initialize LLM client
        self.llm = get_llm_client(db=db)

        # Initialize agents with memory context and adult mode overlay
        self.facilitator = FacilitatorAgent(
            llm_client=self.llm,
            db=db,
            book_id=session.book_id,
            context=agent_context,
            mode=self.mode,
            memory=self.memory,
            allowed_section_ids=self.scope.section_ids,
            allowed_chunk_ids=list(self.scope.spans),
            allowed_spans=self.scope.spans,
            initial_evidence=self.scope.initial_evidence,
            adult_mode=self.is_adult,
        )
        self.close_reader = CloseReaderAgent(
            llm_client=self.llm,
            db=db,
            book_id=session.book_id,
            context=agent_context,
            mode=self.mode,
            memory=self.memory,
            allowed_section_ids=self.scope.section_ids,
            allowed_chunk_ids=list(self.scope.spans),
            allowed_spans=self.scope.spans,
            initial_evidence=self.scope.initial_evidence,
            adult_mode=self.is_adult,
        )
        self.skeptic = SkepticAgent(
            llm_client=self.llm,
            db=db,
            book_id=session.book_id,
            context=agent_context,
            mode=self.mode,
            memory=self.memory,
            allowed_section_ids=self.scope.section_ids,
            allowed_chunk_ids=list(self.scope.spans),
            allowed_spans=self.scope.spans,
            initial_evidence=self.scope.initial_evidence,
            adult_mode=self.is_adult,
        )
        self.after_dark_guide = AfterDarkGuideAgent(
            llm_client=self.llm,
            db=db,
            book_id=session.book_id,
            context=agent_context,
            mode=self.mode,
            memory=self.memory,
            allowed_section_ids=self.scope.section_ids,
            allowed_chunk_ids=list(self.scope.spans),
            allowed_spans=self.scope.spans,
            initial_evidence=self.scope.initial_evidence,
            adult_mode=self.is_adult,
        )

    def _load_memory_context(self) -> MemoryContext | None:
        """Load memory context from database if BookMemory exists for this book."""
        try:
            # Find BookMemory for this book (user_id would need to be added later for multi-user)
            book_memory = (
                self.db.query(BookMemory)
                .filter(BookMemory.book_id == self.session.book_id)
                .first()
            )
            if not book_memory:
                return None

            # Get total reading units for this book
            total_units = (
                self.db.query(ReadingUnit)
                .filter(ReadingUnit.book_id == self.session.book_id)
                .count()
            )

            # Get current reading unit if any
            current_unit = (
                self.db.query(ReadingUnit)
                .filter(ReadingUnit.id == book_memory.current_unit_id)
                .first()
            ) if book_memory.current_unit_id else None

            return build_memory_from_db(book_memory, current_unit, total_units)
        except Exception:
            # If anything fails, just continue without memory
            return None

    async def _classify_turn(
        self, user_content: str, history: list[LLMMessage]
    ) -> dict:
        """
        Classify what kind of response the user's message needs (MARS pattern).

        Uses a cheap, low-token LLM call to decide which agents should respond,
        avoiding unnecessary API calls for simple messages.

        Returns:
            Dict with keys: needs_close_reader (bool), needs_skeptic (bool), reason (str)
        """
        classify_prompt = (
            "Based on this user message in a book discussion, classify what kind "
            "of response is needed.\n"
            "Reply with ONLY a JSON object (no markdown, no explanation):\n"
            '{{\n'
            '    "needs_close_reader": true/false,\n'
            '    "needs_skeptic": true/false,\n'
            '    "reason": "brief explanation"\n'
            '}}\n\n'
            "Guidelines:\n"
            "- needs_close_reader: true if the message involves textual analysis, "
            "specific passages, word choices, patterns, or literary interpretation\n"
            "- needs_skeptic: true if the message makes a debatable claim, a strong "
            "interpretation, or could benefit from an alternative perspective\n"
            "- Both can be false if it's a simple question or greeting\n"
            "- Both can be true for complex analytical claims about the text\n\n"
            'User message: "{user_content}"'
        ).format(user_content=user_content)

        try:
            messages = [
                LLMMessage(
                    role="system", content="You are a brief classifier. Output only JSON."
                ),
                LLMMessage(role="user", content=classify_prompt),
            ]
            response = await self.llm.complete(
                messages, temperature=0.0, max_tokens=150
            )

            # Parse JSON from response, handling possible markdown fencing
            import json as _json

            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            result = _json.loads(response)
            return {
                "needs_close_reader": bool(result.get("needs_close_reader", True)),
                "needs_skeptic": bool(result.get("needs_skeptic", False)),
                "reason": result.get("reason", ""),
            }
        except Exception:
            # Default: include close reader, skip skeptic (safe fallback)
            return {
                "needs_close_reader": True,
                "needs_skeptic": False,
                "reason": "classification failed, using defaults",
            }

    def _build_retrieval_query(
        self, user_content: str, history: list[LLMMessage]
    ) -> str:
        """
        Build a retrieval query that accounts for conversational context.

        When the user's message is short/vague (e.g. "break it down", "tell me
        more", "can you explain?"), the raw text is a poor retrieval query.
        In those cases, we prepend topic keywords from the most recent assistant
        message so the embedding captures what the conversation is actually about.
        """
        # If the message is specific enough, use it as-is
        word_count = len(user_content.split())
        if word_count >= 8:
            return user_content

        # Look for the last substantive assistant message to extract topic context
        for msg in reversed(history):
            if msg.role == "assistant" and len(msg.content) > 50:
                # Take the first ~150 chars as topic context
                topic_snippet = msg.content[:150].strip()
                # Strip any citation markers
                topic_snippet = re.sub(r'\[cite:[^\]]+\]', '', topic_snippet)
                topic_snippet = re.sub(r'\[\d+\]', '', topic_snippet)
                topic_snippet = topic_snippet.strip()
                if topic_snippet:
                    return f"{topic_snippet} | {user_content}"
                break

        return user_content

    async def _get_conversation_history(self) -> list[LLMMessage]:
        """Get conversation history as LLM messages, truncated to budget.

        Applies ``settings.max_history_messages`` to keep context size bounded.
        All messages are still persisted in the DB; only the window sent to
        the LLM is truncated.
        """
        message_query = (
            self.db.query(Message)
            .filter(Message.session_id == self.session.id, Message.content != "")
            .order_by(Message.created_at.desc(), Message.id.desc())
        )
        message_query = self.scope.filter_history(message_query)
        if settings.max_history_messages > 0:
            message_query = message_query.limit(settings.max_history_messages)
        messages = list(reversed(message_query.all()))
        llm_messages = []
        for msg in messages:
            if msg.role == MessageRole.USER:
                role = "user"
            else:
                role = "assistant"
            llm_messages.append(LLMMessage(role=role, content=msg.content))

        # Apply history truncation guardrail
        llm_messages = truncate_history(
            llm_messages, settings.max_history_messages
        )

        recent_ids = {m.id for m in messages[-settings.max_history_messages:]} if settings.max_history_messages > 0 else {m.id for m in messages}
        query = next((m.content for m in reversed(messages) if m.role == MessageRole.USER), "")
        reader_message = next((m for m in reversed(messages) if m.role == MessageRole.USER), None)
        recall = await recall_for_turn(self.db, self.session.book_id, self.scope.section_ids, query, recent_ids, scope=self.scope, reader_message=reader_message)
        if recall:
            # Keep the role prompt as the only system message (Anthropic also
            # expects one). Memory is labelled user data, not a second prompt.
            llm_messages.insert(0, LLMMessage(role="user", content=recall))
        return llm_messages

    @staticmethod
    def _serialize_citations(citations: list[Citation]) -> list[dict]:
        """Serialize Citation objects to dicts for persistence and API responses."""
        return [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "verified": c.verified,
                "match_type": c.match_type,
            }
            for c in citations
        ]

    def _save_message(
        self,
        role: MessageRole,
        content: str,
        citations: list[dict] | None = None,
        metadata_json: dict | None = None,
    ) -> Message:
        """Save a message to the database."""
        message = Message(
            session_id=self.session.id,
            role=role,
            content=content,
            citations=citations,
            metadata_json={**(metadata_json or {}), "reading_scope": self.scope.metadata},
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    @staticmethod
    def _citation_metadata(response: AgentResponse) -> dict | None:
        """Extract citation metrics and token usage from an AgentResponse for metadata_json."""
        metadata: dict = {}
        if response.citation_metrics is not None:
            metadata["citation_metrics"] = response.citation_metrics.to_dict()
        if response.input_tokens or response.output_tokens:
            metadata["token_usage"] = {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.input_tokens + response.output_tokens,
            }
        return metadata or None

    async def start_discussion(self) -> AgentResponse:
        """Start the discussion with opening questions from the facilitator."""
        phase = self.session.current_phase or "warmup"
        response = await self.facilitator.generate_opening_questions(phase)

        # Save facilitator message with full citation metadata
        self._save_message(
            MessageRole.FACILITATOR,
            response.content,
            self._serialize_citations(response.citations),
            metadata_json=self._citation_metadata(response),
        )

        return response

    async def process_user_message(
        self,
        user_content: str,
        include_close_reader: bool = True,
        adaptive: bool = True,
    ) -> list[AgentResponse]:
        """
        Process a user message and generate agent responses.

        Args:
            user_content: The user's message
            include_close_reader: Whether to include close reader response
            adaptive: If True, use MARS-style adaptive agent selection
                      (a cheap classifier decides which agents respond)

        Returns:
            List of agent responses (facilitator, optionally close_reader,
            optionally after_dark_guide, optionally skeptic)
        """
        import uuid

        turn_metrics = TurnMetrics(turn_id=str(uuid.uuid4()))
        turn_metrics.start()

        # Save user message
        self._save_message(MessageRole.USER, user_content)

        # Get conversation history
        history = await self._get_conversation_history()

        # Adaptive agent selection (MARS pattern)
        if adaptive and include_close_reader:
            classification = await self._classify_turn(user_content, history)
            include_close_reader = classification["needs_close_reader"]
            include_skeptic = classification["needs_skeptic"]
        else:
            include_skeptic = False

        responses = []

        # Build a context-aware retrieval query for vague follow-ups
        retrieval_query = self._build_retrieval_query(user_content, history)

        # Get facilitator response (always)
        # Note: BaseAgent.respond_with_retrieval now handles structured
        # JSON parsing, verification with span alignment, and repair internally.
        with turn_metrics.track_stage("facilitator") as stage:
            facilitator_response = await self.facilitator.respond_with_retrieval(
                history,
                query=retrieval_query,
            )
            stage.tokens_in = facilitator_response.input_tokens
            stage.tokens_out = facilitator_response.output_tokens
        self._save_message(
            MessageRole.FACILITATOR,
            facilitator_response.content,
            self._serialize_citations(facilitator_response.citations),
            metadata_json=self._citation_metadata(facilitator_response),
        )
        responses.append(facilitator_response)

        # Optionally get close reader response
        if include_close_reader:
            # Add facilitator response to history for close reader
            history.append(
                LLMMessage(role="assistant", content=facilitator_response.content)
            )

            with turn_metrics.track_stage("close_reader") as stage:
                close_reader_response = await self.close_reader.respond_with_retrieval(
                    history,
                    query=retrieval_query,
                )
                stage.tokens_in = close_reader_response.input_tokens
                stage.tokens_out = close_reader_response.output_tokens
            self._save_message(
                MessageRole.CLOSE_READER,
                close_reader_response.content,
                self._serialize_citations(close_reader_response.citations),
                metadata_json=self._citation_metadata(close_reader_response),
            )
            responses.append(close_reader_response)
            history.append(LLMMessage(role="assistant", content=close_reader_response.content))

        if self.is_adult:
            guide_history = list(history)
            if facilitator_response and not include_close_reader:
                guide_history.append(
                    LLMMessage(role="assistant", content=facilitator_response.content)
                )

            with turn_metrics.track_stage("after_dark_guide") as stage:
                after_dark_response = await self.after_dark_guide.respond_with_retrieval(
                    guide_history,
                    query=retrieval_query,
                )
                stage.tokens_in = after_dark_response.input_tokens
                stage.tokens_out = after_dark_response.output_tokens
            self._save_message(
                MessageRole.AFTER_DARK_GUIDE,
                after_dark_response.content,
                self._serialize_citations(after_dark_response.citations),
                metadata_json=self._citation_metadata(after_dark_response),
            )
            responses.append(after_dark_response)
            history.append(LLMMessage(role="assistant", content=after_dark_response.content))

        # Optionally get skeptic response (only via adaptive selection)
        if include_skeptic:
            # Add previous responses to history for skeptic context
            skeptic_history = list(history)
            if facilitator_response and not any(
                msg.content == facilitator_response.content for msg in skeptic_history
            ):
                skeptic_history.append(
                    LLMMessage(role="assistant", content=facilitator_response.content)
                )

            with turn_metrics.track_stage("skeptic") as stage:
                skeptic_response = await self.skeptic.respond_with_retrieval(
                    skeptic_history,
                    query=retrieval_query,
                )
                stage.tokens_in = skeptic_response.input_tokens
                stage.tokens_out = skeptic_response.output_tokens
            self._save_message(
                MessageRole.SKEPTIC,
                skeptic_response.content,
                self._serialize_citations(skeptic_response.citations),
                metadata_json=self._citation_metadata(skeptic_response),
            )
            responses.append(skeptic_response)

        turn_metrics.finish()
        turn_metrics.check_budgets()
        _logger.info(
            "[TurnMetrics] turn_id=%s total_ms=%.1f stages=%s",
            turn_metrics.turn_id,
            turn_metrics.total_ms,
            [s.to_dict() for s in turn_metrics.stages],
        )

        return responses

    async def stream_user_message(
        self,
        user_content: str,
        include_close_reader: bool = True,
        adaptive: bool = True,
    ) -> AsyncIterator[dict]:
        """
        Stream agent responses for a user message.

        Yields SSE-friendly event dicts with hardened protocol fields:
          - event_id: unique within this turn (e.g. "evt_1"); durable replay is not implemented
          - turn_id: unique per user turn (uuid4), groups all events in one turn
          - agent_id: role string identifying the agent (on agent-scoped events)
          - sequence: monotonically increasing int for ordering / dedup

        Event types:
          - {"type":"turn_classification", ..., "classification":{...}}  (adaptive only)
          - {"type":"message_start", ..., "voice":...}
          - {"type":"message_delta", ..., "delta":...}
          - {"type":"sentence_ready", ..., "sentence":..., "sentence_index":..., "voice":...}
          - {"type":"message_end", ..., "content":..., "citations":[...]}
          - {"type":"agent_error", ..., "error":...}  (partial failure)
          - {"type":"done", ...}

        The ``sentence_ready`` events use finalized, citation-checked prose and
        are emitted immediately before ``message_end``. Each includes the
        agent's assigned ``voice`` for consistent per-agent TTS.
        """
        import uuid

        turn_id = str(uuid.uuid4())
        event_seq = 0
        turn_metrics = TurnMetrics(turn_id=turn_id)
        turn_metrics.start()

        self._save_message(MessageRole.USER, user_content)

        history = await self._get_conversation_history()

        # Build a context-aware retrieval query for vague follow-ups
        retrieval_query = self._build_retrieval_query(user_content, history)

        # Adaptive agent selection (MARS pattern)
        include_skeptic = False
        classification = None
        if adaptive and include_close_reader:
            classification = await self._classify_turn(user_content, history)
            include_close_reader = classification["needs_close_reader"]
            include_skeptic = classification["needs_skeptic"]

            # Emit classification event so the frontend knows which agents will respond
            event_seq += 1
            yield {
                "type": "turn_classification",
                "event_id": f"evt_{event_seq}",
                "turn_id": turn_id,
                "sequence": event_seq,
                "classification": classification,
            }

        async def stream_agent(agent, role: str, conversation_history: list[LLMMessage] | None = None):
            nonlocal event_seq

            voice = AGENT_VOICES.get(role, "nova")

            event_seq += 1
            yield {
                "type": "message_start",
                "sentence_events": True,
                "event_id": f"evt_{event_seq}",
                "turn_id": turn_id,
                "agent_id": role,
                "sequence": event_seq,
                "role": role,
                "voice": voice,
                "session_id": self.session.id,
            }

            chunks_list: list[str] = []
            prose_stream = AnalysisStream()
            try:
                async with aclosing(agent.stream_with_retrieval(
                    conversation_history if conversation_history is not None else history,
                    query=retrieval_query,
                )) as response:
                    async for delta in response:
                        chunks_list.append(delta)
                        visible = prose_stream.feed(delta)
                        if not visible:
                            continue
                        if turn_metrics.ttft_ms == 0.0:
                            turn_metrics.record_ttft()
                        event_seq += 1
                        yield {
                            "type": "message_delta",
                            "event_id": f"evt_{event_seq}",
                            "turn_id": turn_id,
                            "agent_id": role,
                            "sequence": event_seq,
                            "role": role,
                            "session_id": self.session.id,
                            "delta": visible,
                        }

            except Exception as e:
                # Partial failure: rollback any poisoned transaction state so
                # subsequent agents can still use the DB session.
                try:
                    self.db.rollback()
                except Exception:
                    pass
                event_seq += 1
                yield {
                    "type": "agent_error",
                    "event_id": f"evt_{event_seq}",
                    "turn_id": turn_id,
                    "agent_id": role,
                    "sequence": event_seq,
                    "role": role,
                    "session_id": self.session.id,
                    "error": str(e),
                }
                return  # Skip message_end for this agent

            raw_text = "".join(chunks_list)
            clean_text, citations = parse_response_auto(raw_text)

            clean_text, citation_objects, cit_metrics = await agent._verify_and_maybe_repair(
                raw_text, clean_text, citations,
            )
            citations = self._serialize_citations(citation_objects)

            # Capture token usage from the stream (if the provider reported it)
            stream_usage = getattr(agent, "last_stream_usage", None)
            input_tokens = stream_usage.input_tokens if stream_usage else 0
            output_tokens = stream_usage.output_tokens if stream_usage else 0

            role_enum = MessageRole[role.upper()]
            msg_metadata: dict | None = {}
            if cit_metrics is not None:
                msg_metadata["citation_metrics"] = cit_metrics.to_dict()
            if input_tokens or output_tokens:
                msg_metadata["token_usage"] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            if not msg_metadata:
                msg_metadata = None
            saved_message = self._save_message(
                role_enum,
                clean_text,
                citations,
                metadata_json=msg_metadata,
            )

            splitter = SentenceSplitter()
            sentences = splitter.feed(clean_text)
            remainder = splitter.flush()
            if remainder:
                sentences.append(remainder)
            for sentence_index, sentence in enumerate(sentences):
                event_seq += 1
                yield {"type": "sentence_ready", "event_id": f"evt_{event_seq}",
                       "turn_id": turn_id, "agent_id": role, "sequence": event_seq,
                       "role": role, "voice": voice, "session_id": self.session.id,
                       "sentence": sentence, "sentence_index": sentence_index}

            event_seq += 1
            yield {
                "type": "message_end",
                "event_id": f"evt_{event_seq}",
                "turn_id": turn_id,
                "agent_id": role,
                "sequence": event_seq,
                "role": role,
                "session_id": self.session.id,
                "message_id": saved_message.id,
                "content": clean_text,
                "citations": citations,
                "citation_quality": cit_metrics.to_dict() if cit_metrics is not None else None,
                "token_usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            }

        # Stream facilitator (always)
        facilitator_text = None
        close_reader_text = None
        after_dark_text = None
        with turn_metrics.track_stage("facilitator") as fac_stage:
            async with aclosing(stream_agent(self.facilitator, "facilitator")) as response:
                async for event in response:
                    if event["type"] == "message_end":
                        facilitator_text = event["content"]
                        fac_stage.tokens_in = event.get("token_usage", {}).get("input_tokens", 0)
                        fac_stage.tokens_out = event.get("token_usage", {}).get("output_tokens", 0)
                    yield event

        # Stream close_reader if needed
        if include_close_reader:
            if facilitator_text is not None:
                history.append(LLMMessage(role="assistant", content=facilitator_text))
            with turn_metrics.track_stage("close_reader") as cr_stage:
                async with aclosing(stream_agent(self.close_reader, "close_reader", history)) as response:
                    async for event in response:
                        if event["type"] == "message_end":
                            close_reader_text = event["content"]
                            cr_stage.tokens_in = event.get("token_usage", {}).get("input_tokens", 0)
                            cr_stage.tokens_out = event.get("token_usage", {}).get("output_tokens", 0)
                        yield event

        if self.is_adult:
            guide_history = list(history)
            if facilitator_text is not None and not include_close_reader:
                guide_history.append(LLMMessage(role="assistant", content=facilitator_text))
            if close_reader_text is not None:
                guide_history.append(LLMMessage(role="assistant", content=close_reader_text))
            with turn_metrics.track_stage("after_dark_guide") as ad_stage:
                async with aclosing(stream_agent(
                    self.after_dark_guide,
                    "after_dark_guide",
                    guide_history,
                )) as response:
                    async for event in response:
                        if event["type"] == "message_end":
                            after_dark_text = event["content"]
                            ad_stage.tokens_in = event.get("token_usage", {}).get("input_tokens", 0)
                            ad_stage.tokens_out = event.get("token_usage", {}).get("output_tokens", 0)
                        yield event

        # Stream skeptic if needed (only via adaptive selection)
        if include_skeptic:
            # Ensure facilitator context is in history for skeptic
            if facilitator_text is not None and not include_close_reader:
                history.append(LLMMessage(role="assistant", content=facilitator_text))
            if close_reader_text is not None:
                history.append(LLMMessage(role="assistant", content=close_reader_text))
            if after_dark_text is not None:
                history.append(LLMMessage(role="assistant", content=after_dark_text))
            with turn_metrics.track_stage("skeptic") as sk_stage:
                async with aclosing(stream_agent(self.skeptic, "skeptic", history)) as response:
                    async for event in response:
                        if event["type"] == "message_end":
                            sk_stage.tokens_in = event.get("token_usage", {}).get("input_tokens", 0)
                            sk_stage.tokens_out = event.get("token_usage", {}).get("output_tokens", 0)
                        yield event

        turn_metrics.finish()
        violations = turn_metrics.check_budgets()
        _logger.info(
            "[TurnMetrics] turn_id=%s total_ms=%.1f ttft_ms=%.1f stages=%s",
            turn_metrics.turn_id,
            turn_metrics.total_ms,
            turn_metrics.ttft_ms,
            [s.to_dict() for s in turn_metrics.stages],
        )

        event_seq += 1
        yield {
            "type": "done",
            "event_id": f"evt_{event_seq}",
            "turn_id": turn_id,
            "sequence": event_seq,
            "turn_metrics": turn_metrics.to_dict(),
        }

    async def get_skeptic_response(self, claim: str) -> AgentResponse:
        """Get a skeptic response to challenge a claim."""
        response = await self.skeptic.challenge_claim(claim)
        self._save_message(
            MessageRole.SKEPTIC,
            response.content,
            self._serialize_citations(response.citations),
            metadata_json=self._citation_metadata(response),
        )
        return response

    def advance_phase(self) -> str:
        """Advance to the next discussion phase."""
        mode_config = DISCUSSION_PROMPTS.get(self.mode, DISCUSSION_PROMPTS["guided"])
        phases = mode_config["phases"]

        current_idx = 0
        if self.session.current_phase in phases:
            current_idx = phases.index(self.session.current_phase)

        next_idx = min(current_idx + 1, len(phases) - 1)
        new_phase = phases[next_idx]

        self.session.current_phase = new_phase
        self.db.commit()

        return new_phase

    async def generate_summary(self) -> str:
        """Generate a summary of the discussion."""
        history = await self._get_conversation_history()  # already truncated

        summary_prompt = """Please provide a concise summary of this book discussion.

Include:
- Key insights that emerged
- Important textual passages that were discussed
- Questions that remain open
- Themes or patterns identified

Format as a brief, readable summary (2-3 paragraphs)."""

        messages = [
            LLMMessage(role="system", content="You are summarizing a book discussion."),
            *history,
            LLMMessage(role="user", content=summary_prompt),
        ]

        summary = await self.llm.complete(
            messages, temperature=0.5, max_tokens=settings.max_tokens_per_turn
        )

        # Save summary to session
        self.session.summary = summary
        self.db.commit()

        return summary
