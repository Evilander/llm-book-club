"""Tests for structured JSON response parsing and the auto-detection fallback.

Covers:
  - parse_structured_response: JSON parsing with markdown fence handling
  - parse_response_auto: auto-detection (JSON first, regex fallback)
  - compute_span_alignment: exact and normalized span finding
"""
import json
import pytest

from app.discussion.agents import (
    parse_structured_response,
    parse_response_auto,
    compute_span_alignment,
)


# =========================================================================
# parse_structured_response
# =========================================================================


class TestParseStructuredResponse:
    """Test JSON-based structured response parsing."""

    def test_parse_valid_json(self):
        response = json.dumps({
            "analysis": "The author uses vivid imagery [1] to create atmosphere.",
            "citations": [
                {"marker": 1, "chunk_id": "chunk-123", "quote": "morning sun cast shadows"}
            ]
        })
        result = parse_structured_response(response)
        assert result is not None
        text, citations = result
        assert "vivid imagery" in text
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "chunk-123"
        assert citations[0]["text"] == "morning sun cast shadows"
        assert citations[0]["marker"] == 1

    def test_parse_json_with_markdown_wrapper(self):
        inner = json.dumps({
            "analysis": "Test analysis [1].",
            "citations": [{"marker": 1, "chunk_id": "c1", "quote": "test quote"}]
        })
        response = f"```json\n{inner}\n```"
        result = parse_structured_response(response)
        assert result is not None
        text, citations = result
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "c1"

    def test_parse_json_with_plain_fence(self):
        inner = json.dumps({
            "analysis": "Fenced response.",
            "citations": []
        })
        response = f"```\n{inner}\n```"
        result = parse_structured_response(response)
        assert result is not None
        text, citations = result
        assert "Fenced response" in text
        assert len(citations) == 0

    def test_returns_none_for_non_json(self):
        response = "This is just regular text, not JSON at all."
        result = parse_structured_response(response)
        assert result is None

    def test_returns_none_for_malformed_json(self):
        response = '{"analysis": "missing closing brace"'
        result = parse_structured_response(response)
        assert result is None

    def test_returns_none_for_non_dict_json(self):
        response = json.dumps(["a", "list", "not", "dict"])
        result = parse_structured_response(response)
        assert result is None

    def test_returns_none_for_missing_analysis_key(self):
        response = json.dumps({"text": "wrong key", "citations": []})
        result = parse_structured_response(response)
        assert result is None

    def test_empty_citations_list(self):
        response = json.dumps({
            "analysis": "No citations needed for this response.",
            "citations": []
        })
        result = parse_structured_response(response)
        assert result is not None
        text, citations = result
        assert "No citations" in text
        assert len(citations) == 0

    def test_missing_citations_key_returns_empty_list(self):
        response = json.dumps({"analysis": "Response without citations key."})
        result = parse_structured_response(response)
        assert result is not None
        text, citations = result
        assert "without citations" in text
        assert len(citations) == 0

    def test_multiple_citations(self):
        response = json.dumps({
            "analysis": "First point [1] and second point [2].",
            "citations": [
                {"marker": 1, "chunk_id": "c1", "quote": "first quote"},
                {"marker": 2, "chunk_id": "c2", "quote": "second quote"},
            ]
        })
        result = parse_structured_response(response)
        assert result is not None
        _, citations = result
        assert len(citations) == 2
        assert citations[0]["chunk_id"] == "c1"
        assert citations[1]["chunk_id"] == "c2"

    def test_skips_invalid_citation_entries(self):
        """Non-dict entries or entries missing chunk_id/quote should be skipped."""
        response = json.dumps({
            "analysis": "Has some invalid citations [1] [2].",
            "citations": [
                {"marker": 1, "chunk_id": "c1", "quote": "valid"},
                "not a dict",
                {"marker": 3, "chunk_id": "", "quote": "missing id"},
                {"marker": 4, "chunk_id": "c4", "quote": ""},
            ]
        })
        result = parse_structured_response(response)
        assert result is not None
        _, citations = result
        # Only the first one is valid
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "c1"

    def test_strips_whitespace_from_chunk_id_and_quote(self):
        response = json.dumps({
            "analysis": "Test [1].",
            "citations": [
                {"marker": 1, "chunk_id": "  c1  ", "quote": "  some text  "}
            ]
        })
        result = parse_structured_response(response)
        assert result is not None
        _, citations = result
        assert citations[0]["chunk_id"] == "c1"
        assert citations[0]["text"] == "some text"


# =========================================================================
# parse_response_auto
# =========================================================================


class TestParseResponseAuto:
    """Test auto-detection: tries structured JSON first, falls back to regex."""

    def test_prefers_structured_json(self):
        response = json.dumps({
            "analysis": "Structured response [1].",
            "citations": [
                {"marker": 1, "chunk_id": "c1", "quote": "the text"}
            ]
        })
        text, citations = parse_response_auto(response)
        assert "Structured response" in text
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "c1"

    def test_falls_back_to_regex(self):
        response = 'Regular text with [cite: chunk-1, "quoted text"] citation.'
        text, citations = parse_response_auto(response)
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "chunk-1"
        assert citations[0]["text"] == "quoted text"

    def test_plain_text_no_citations(self):
        response = "Just a plain text response with no markers."
        text, citations = parse_response_auto(response)
        assert text == response
        assert len(citations) == 0


# =========================================================================
# compute_span_alignment
# =========================================================================


class TestComputeSpanAlignment:
    """Test span alignment computation (finding quote within chunk text)."""

    def test_exact_verbatim_match(self):
        chunk_text = "The morning sun cast long shadows across the empty courtyard."
        quote = "long shadows across"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        start, end, match_type = result
        assert match_type == "exact"
        assert chunk_text[start:end] == quote

    def test_exact_match_at_beginning(self):
        chunk_text = "The morning sun cast long shadows."
        quote = "The morning sun"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        start, end, match_type = result
        assert start == 0
        assert match_type == "exact"

    def test_exact_match_at_end(self):
        chunk_text = "The morning sun cast long shadows."
        quote = "long shadows."
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        _, _, match_type = result
        assert match_type == "exact"

    def test_normalized_match_case_insensitive(self):
        chunk_text = "The Morning Sun cast long shadows."
        quote = "the morning sun cast"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        start, end, match_type = result
        assert match_type == "normalized"

    def test_normalized_match_extra_whitespace(self):
        chunk_text = "The  morning   sun cast long shadows."
        quote = "morning sun cast"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        _, _, match_type = result
        # Could be exact or normalized depending on the text
        assert match_type in ("exact", "normalized")

    def test_no_match_returns_none(self):
        chunk_text = "The morning sun cast long shadows."
        quote = "This text is not in the chunk at all."
        result = compute_span_alignment(chunk_text, quote)
        assert result is None

    def test_empty_quote_returns_none(self):
        chunk_text = "Some text."
        result = compute_span_alignment(chunk_text, "")
        assert result is None

    def test_empty_chunk_returns_none(self):
        result = compute_span_alignment("", "some quote")
        assert result is None

    def test_both_empty_returns_none(self):
        result = compute_span_alignment("", "")
        assert result is None

    def test_full_chunk_as_quote(self):
        chunk_text = "The morning sun cast long shadows."
        result = compute_span_alignment(chunk_text, chunk_text)
        assert result is not None
        start, end, match_type = result
        assert match_type == "exact"
        assert start == 0
        assert end == len(chunk_text)
