"""Token budget guardrails for controlling LLM call costs.

Provides simple token estimation and functions to truncate conversation
history and retrieved evidence so that no single LLM call sends an
unbounded amount of context.

Token estimation uses the chars/4 heuristic (no external dependency).
"""
from __future__ import annotations

import logging
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

    This intentionally over-counts slightly, which is the safe direction
    for budget enforcement.  For precise counts, swap in tiktoken later.
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
        A prefix of *results* that fits within the budget.
    """
    if max_tokens <= 0:
        return results  # disabled

    kept: list[SearchResult] = []
    running_tokens = 0

    for result in results:
        chunk_tokens = estimate_tokens(result.text)
        if running_tokens + chunk_tokens > max_tokens and kept:
            # Already have at least one result; stop adding
            break
        kept.append(result)
        running_tokens += chunk_tokens

    if len(kept) < len(results):
        logger.info(
            "Trimmed evidence from %d to %d chunks (~%d tokens, budget %d).",
            len(results),
            len(kept),
            running_tokens,
            max_tokens,
        )

    return kept
