"""Tests for the token budget guardrails module.

Covers:
  - estimate_tokens: chars/4 heuristic with min-1 floor
  - estimate_messages_tokens: sum across messages with per-message overhead
  - truncate_history: keep last N messages, disabled when max_messages <= 0
  - trim_evidence: keep top-k results within token budget, disabled when max_tokens <= 0
"""
import logging

import pytest

from app.discussion.token_budget import (
    estimate_tokens,
    estimate_messages_tokens,
    truncate_history,
    trim_evidence,
)
from app.providers.llm.base import LLMMessage
from app.retrieval.search import SearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(role: str, content: str) -> LLMMessage:
    """Create an LLMMessage with the given role and content."""
    return LLMMessage(role=role, content=content)


def _make_result(chunk_id: str, text: str, score: float = 0.9) -> SearchResult:
    """Create a SearchResult with the given text and sensible defaults."""
    return SearchResult(
        chunk_id=chunk_id,
        section_id="sec-1",
        section_title="Chapter 1",
        text=text,
        char_start=0,
        char_end=len(text),
        source_ref=None,
        score=score,
    )


# =========================================================================
# estimate_tokens
# =========================================================================


class TestEstimateTokens:
    """Test the chars/4 token estimation heuristic."""

    def test_empty_string_returns_one(self):
        """Empty string has zero chars but the function floors at 1."""
        assert estimate_tokens("") == 1

    def test_single_character(self):
        """A single character: len=1, 1//4=0, floored to 1."""
        assert estimate_tokens("a") == 1

    def test_three_characters(self):
        """Three characters: 3//4=0, floored to 1."""
        assert estimate_tokens("abc") == 1

    def test_four_characters(self):
        """Four characters: 4//4=1, exactly at the boundary."""
        assert estimate_tokens("abcd") == 1

    def test_five_characters(self):
        """Five characters: 5//4=1."""
        assert estimate_tokens("abcde") == 1

    def test_eight_characters(self):
        """Eight characters: 8//4=2."""
        assert estimate_tokens("abcdefgh") == 2

    @pytest.mark.parametrize(
        "length, expected",
        [
            (0, 1),      # floor
            (1, 1),      # floor
            (3, 1),      # floor
            (4, 1),      # boundary
            (7, 1),      # just under 2
            (8, 2),      # boundary
            (100, 25),
            (1000, 250),
            (4000, 1000),
        ],
    )
    def test_various_lengths(self, length, expected):
        """Parametrized test across a range of input lengths."""
        text = "x" * length
        assert estimate_tokens(text) == expected

    def test_long_text(self):
        """Large input should scale linearly: 40000 chars -> 10000 tokens."""
        text = "a" * 40_000
        assert estimate_tokens(text) == 10_000

    def test_unicode_characters(self):
        """Unicode characters are still single chars in Python, so len() counts them."""
        text = "\u00e9\u00e9\u00e9\u00e9"  # 4 chars
        assert estimate_tokens(text) == 1

    def test_return_type_is_int(self):
        """The return value must always be an integer."""
        result = estimate_tokens("hello world")
        assert isinstance(result, int)


# =========================================================================
# estimate_messages_tokens
# =========================================================================


class TestEstimateMessagesTokens:
    """Test token estimation across a list of LLM messages."""

    def test_empty_list(self):
        """No messages means zero tokens."""
        assert estimate_messages_tokens([]) == 0

    def test_single_message_includes_overhead(self):
        """A single message should include the 4-token overhead plus content tokens.

        Content "abcdefgh" = 8 chars -> 2 tokens.
        Total = 4 (overhead) + 2 = 6.
        """
        msgs = [_make_message("user", "abcdefgh")]
        assert estimate_messages_tokens(msgs) == 6

    def test_single_message_short_content(self):
        """Content "a" = 1 char -> 1 token (floor).
        Total = 4 (overhead) + 1 = 5.
        """
        msgs = [_make_message("user", "a")]
        assert estimate_messages_tokens(msgs) == 5

    def test_single_message_empty_content(self):
        """Empty content = 0 chars -> 1 token (floor).
        Total = 4 (overhead) + 1 = 5.
        """
        msgs = [_make_message("user", "")]
        assert estimate_messages_tokens(msgs) == 5

    def test_multiple_messages(self):
        """Two messages, each with 8-char content (2 tokens).
        Total = (4 + 2) + (4 + 2) = 12.
        """
        msgs = [
            _make_message("user", "abcdefgh"),
            _make_message("assistant", "12345678"),
        ]
        assert estimate_messages_tokens(msgs) == 12

    def test_overhead_accumulates_per_message(self):
        """Four messages with empty content.
        Each: 4 overhead + 1 (floor) = 5 tokens.
        Total = 20.
        """
        msgs = [_make_message("user", "") for _ in range(4)]
        assert estimate_messages_tokens(msgs) == 20

    def test_mixed_roles(self):
        """Role name does not affect token count; only content matters."""
        msgs = [
            _make_message("system", "abcdefgh"),       # 4 + 2 = 6
            _make_message("user", "abcdefghijklmnop"),  # 4 + 4 = 8
            _make_message("assistant", "abcd"),         # 4 + 1 = 5
        ]
        assert estimate_messages_tokens(msgs) == 19


# =========================================================================
# truncate_history
# =========================================================================


class TestTruncateHistory:
    """Test conversation history truncation."""

    def test_under_limit_is_noop(self):
        """When history has fewer messages than the limit, return all."""
        history = [
            _make_message("user", "hello"),
            _make_message("assistant", "hi"),
        ]
        result = truncate_history(history, max_messages=5)
        assert len(result) == 2
        assert result is history  # same object, not a copy

    def test_exact_limit_is_noop(self):
        """When history length equals the limit exactly, return all."""
        history = [
            _make_message("user", "hello"),
            _make_message("assistant", "hi"),
            _make_message("user", "bye"),
        ]
        result = truncate_history(history, max_messages=3)
        assert len(result) == 3
        assert result is history

    def test_over_limit_keeps_most_recent(self):
        """When history exceeds limit, keep the last N messages."""
        history = [
            _make_message("user", "first"),       # dropped
            _make_message("assistant", "second"),  # dropped
            _make_message("user", "third"),        # kept
            _make_message("assistant", "fourth"),  # kept
        ]
        result = truncate_history(history, max_messages=2)
        assert len(result) == 2
        assert result[0].content == "third"
        assert result[1].content == "fourth"

    def test_over_limit_drops_oldest(self):
        """Dropped messages should be the earliest ones."""
        history = [_make_message("user", f"msg-{i}") for i in range(10)]
        result = truncate_history(history, max_messages=3)
        assert len(result) == 3
        assert result[0].content == "msg-7"
        assert result[1].content == "msg-8"
        assert result[2].content == "msg-9"

    def test_disabled_when_zero(self):
        """max_messages=0 disables truncation; return full history."""
        history = [_make_message("user", f"msg-{i}") for i in range(20)]
        result = truncate_history(history, max_messages=0)
        assert len(result) == 20
        assert result is history

    def test_disabled_when_negative(self):
        """max_messages=-1 disables truncation; return full history."""
        history = [_make_message("user", f"msg-{i}") for i in range(5)]
        result = truncate_history(history, max_messages=-1)
        assert len(result) == 5
        assert result is history

    def test_empty_history(self):
        """Empty history returns empty list regardless of limit."""
        result = truncate_history([], max_messages=10)
        assert result == []

    def test_empty_history_with_zero_limit(self):
        """Empty history with disabled limit returns empty list."""
        result = truncate_history([], max_messages=0)
        assert result == []

    def test_max_messages_one(self):
        """Limit of 1 keeps only the very last message."""
        history = [
            _make_message("user", "old"),
            _make_message("assistant", "latest"),
        ]
        result = truncate_history(history, max_messages=1)
        assert len(result) == 1
        assert result[0].content == "latest"

    def test_logs_when_truncating(self, caplog):
        """Truncation should emit an INFO log message."""
        history = [_make_message("user", f"msg-{i}") for i in range(5)]
        with caplog.at_level(logging.INFO, logger="app.discussion.token_budget"):
            truncate_history(history, max_messages=2)
        assert "Truncating conversation history" in caplog.text
        assert "keeping 2 of 5" in caplog.text
        assert "dropped 3 oldest" in caplog.text

    def test_no_log_when_under_limit(self, caplog):
        """No truncation means no log message."""
        history = [_make_message("user", "hi")]
        with caplog.at_level(logging.INFO, logger="app.discussion.token_budget"):
            truncate_history(history, max_messages=10)
        assert "Truncating" not in caplog.text


# =========================================================================
# trim_evidence
# =========================================================================


class TestTrimEvidence:
    """Test search result trimming by token budget."""

    def test_under_budget_is_noop(self):
        """When total tokens are within budget, return all results."""
        results = [
            _make_result("c1", "a" * 40, score=0.9),   # 10 tokens
            _make_result("c2", "b" * 40, score=0.8),   # 10 tokens
        ]
        trimmed = trim_evidence(results, max_tokens=100)
        assert len(trimmed) == 2

    def test_exact_budget_keeps_all(self):
        """When total tokens exactly equal the budget, keep everything."""
        # Each result: 20 chars -> 5 tokens. Two results -> 10 tokens total.
        results = [
            _make_result("c1", "a" * 20, score=0.9),
            _make_result("c2", "b" * 20, score=0.8),
        ]
        trimmed = trim_evidence(results, max_tokens=10)
        assert len(trimmed) == 2

    def test_over_budget_trims_lower_ranked(self):
        """When results exceed budget, drop lower-ranked results."""
        results = [
            _make_result("c1", "a" * 40, score=0.9),   # 10 tokens
            _make_result("c2", "b" * 40, score=0.8),   # 10 tokens -> total 20
            _make_result("c3", "c" * 40, score=0.7),   # 10 tokens -> total 30
        ]
        trimmed = trim_evidence(results, max_tokens=15)
        # Only the first result fits within 15 tokens
        assert len(trimmed) == 1
        assert trimmed[0].chunk_id == "c1"

    def test_single_result_always_kept(self):
        """A single result is always kept, even if it exceeds the budget.

        The code only breaks when 'kept' is non-empty, so the first result
        is always included regardless of its size.
        """
        results = [_make_result("c1", "a" * 400, score=0.9)]  # 100 tokens
        trimmed = trim_evidence(results, max_tokens=5)
        assert len(trimmed) == 1
        assert trimmed[0].chunk_id == "c1"

    def test_first_result_always_kept_even_when_oversized(self):
        """Even with multiple results, the first is always kept.

        The first result (200 tokens) exceeds the budget (10), but it is
        still kept because the 'and kept' guard prevents dropping it.
        """
        results = [
            _make_result("c1", "a" * 800, score=0.9),  # 200 tokens
            _make_result("c2", "b" * 40, score=0.8),    # 10 tokens
        ]
        trimmed = trim_evidence(results, max_tokens=10)
        assert len(trimmed) == 1
        assert trimmed[0].chunk_id == "c1"

    def test_disabled_when_zero(self):
        """max_tokens=0 disables trimming; return all results."""
        results = [
            _make_result("c1", "a" * 4000, score=0.9),
            _make_result("c2", "b" * 4000, score=0.8),
        ]
        trimmed = trim_evidence(results, max_tokens=0)
        assert len(trimmed) == 2

    def test_disabled_when_negative(self):
        """max_tokens=-1 disables trimming; return all results."""
        results = [
            _make_result("c1", "a" * 4000, score=0.9),
        ]
        trimmed = trim_evidence(results, max_tokens=-1)
        assert len(trimmed) == 1

    def test_empty_results(self):
        """Empty input returns empty output."""
        trimmed = trim_evidence([], max_tokens=100)
        assert trimmed == []

    def test_empty_results_with_zero_budget(self):
        """Empty input with disabled budget returns empty output."""
        trimmed = trim_evidence([], max_tokens=0)
        assert trimmed == []

    def test_preserves_order(self):
        """Returned results should maintain the original relevance ordering."""
        results = [
            _make_result("c1", "a" * 20, score=0.95),  # 5 tokens
            _make_result("c2", "b" * 20, score=0.90),  # 5 tokens
            _make_result("c3", "c" * 20, score=0.85),  # 5 tokens
        ]
        trimmed = trim_evidence(results, max_tokens=12)
        assert len(trimmed) == 2
        assert trimmed[0].chunk_id == "c1"
        assert trimmed[1].chunk_id == "c2"

    def test_many_small_results(self):
        """Many small results should accumulate until budget is reached."""
        # Each result: 4 chars -> 1 token
        results = [_make_result(f"c{i}", "abcd", score=1.0 - i * 0.01) for i in range(20)]
        trimmed = trim_evidence(results, max_tokens=5)
        assert len(trimmed) == 5

    def test_logs_when_trimming(self, caplog):
        """Trimming should emit an INFO log message."""
        results = [
            _make_result("c1", "a" * 40, score=0.9),
            _make_result("c2", "b" * 40, score=0.8),
            _make_result("c3", "c" * 40, score=0.7),
        ]
        with caplog.at_level(logging.INFO, logger="app.discussion.token_budget"):
            trim_evidence(results, max_tokens=15)
        assert "Trimmed evidence" in caplog.text
        assert "from 3 to 1" in caplog.text

    def test_no_log_when_under_budget(self, caplog):
        """No trimming means no log message."""
        results = [_make_result("c1", "a" * 20, score=0.9)]
        with caplog.at_level(logging.INFO, logger="app.discussion.token_budget"):
            trim_evidence(results, max_tokens=1000)
        assert "Trimmed" not in caplog.text

    def test_budget_boundary_second_result_exactly_fits(self):
        """When the second result fills the budget exactly, it should be kept."""
        # First: 8 chars -> 2 tokens. Second: 12 chars -> 3 tokens. Total = 5.
        results = [
            _make_result("c1", "a" * 8, score=0.9),
            _make_result("c2", "b" * 12, score=0.8),
        ]
        trimmed = trim_evidence(results, max_tokens=5)
        assert len(trimmed) == 2

    def test_budget_boundary_second_result_one_over(self):
        """When the second result pushes one token over budget, it is dropped."""
        # First: 8 chars -> 2 tokens. Second: 16 chars -> 4 tokens. Total would be 6.
        results = [
            _make_result("c1", "a" * 8, score=0.9),
            _make_result("c2", "b" * 16, score=0.8),
        ]
        trimmed = trim_evidence(results, max_tokens=5)
        assert len(trimmed) == 1
        assert trimmed[0].chunk_id == "c1"
