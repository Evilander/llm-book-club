"""Token budget guardrails for controlling LLM call costs.

Provides simple token estimation and functions to truncate conversation
history and retrieved evidence so that no single LLM call sends an
unbounded amount of context.

Token estimation uses the chars/4 heuristic (no external dependency).
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..providers.llm.base import LLMMessage
    from ..retrieval.search import SearchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text* using the chars/4 heuristic.

    This is an approximation, particularly for non-Latin scripts; it is not
    a provider token count. Evidence also has a deterministic character cap.
    """
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[LLMMessage]) -> int:
    """Estimate total tokens across a list of LLM messages."""
    total = 0
    for msg in messages:
        # ~4 tokens overhead per message for role/delimiters
        total += 4 + estimate_tokens(msg.content)
    return total


# ---------------------------------------------------------------------------
# Conversation history truncation
# ---------------------------------------------------------------------------

def truncate_history(
    history: list[LLMMessage],
    max_messages: int,
) -> list[LLMMessage]:
    """Truncate conversation history to the last *max_messages* entries.

    Keeps the most recent messages so the model has the freshest context.
    The system prompt is NOT part of *history* (it is prepended separately
    by the agent), so this function only deals with user/assistant turns.

    Args:
        history: List of user/assistant LLMMessage objects (no system msg).
        max_messages: Maximum number of messages to keep.

    Returns:
        A (possibly shorter) list containing the last *max_messages* items.
    """
    if max_messages <= 0:
        return history  # disabled

    if len(history) <= max_messages:
        return history

    dropped = len(history) - max_messages
    logger.info(
        "Truncating conversation history: keeping %d of %d messages (dropped %d oldest).",
        max_messages,
        len(history),
        dropped,
    )
    return history[-max_messages:]


# ---------------------------------------------------------------------------
# Retrieved evidence trimming
# ---------------------------------------------------------------------------

def trim_evidence(
    results: list[SearchResult],
    max_tokens: int,
) -> list[SearchResult]:
    """Trim search results so their combined text fits within *max_tokens*.

    Results are assumed to be sorted by relevance (best first).  Lower-ranked
    results are dropped first to stay within budget.

    Args:
        results: Search results ordered by relevance (best first).
        max_tokens: Maximum estimated token budget for all evidence text.

    Returns:
        A prefix of *results* that fits within the character allowance. An
        oversized first result is copied and clipped; sources are not mutated.
    """
    if max_tokens <= 0:
        return results  # disabled

    kept: list[SearchResult] = []
    running_tokens = 0
    running_chars = 0

    for result in results:
        chunk_tokens = estimate_tokens(result.text)
        if running_chars + len(result.text) > max_tokens * 4:
            if not kept:
                from .citation_spans import grapheme_boundaries
                end = max(n for n in grapheme_boundaries(result.text) if n <= max_tokens * 4)
                if end:
                    kept.append(replace(result, text=result.text[:end], char_end=result.char_start + end))
            break
        kept.append(result)
        running_tokens += chunk_tokens
        running_chars += len(result.text)

    if len(kept) < len(results):
        logger.info(
            "Trimmed evidence from %d to %d chunks (~%d tokens, budget %d).",
            len(results),
            len(kept),
            running_tokens,
            max_tokens,
        )

    return kept
