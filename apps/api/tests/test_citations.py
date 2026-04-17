"""Tests for citation parsing, verification, and span alignment.

Covers:
  - parse_citations (regex-based backward-compatible parser)
  - normalize_text (unicode/whitespace normalization)
  - verify_citations (exact + fuzzy matching against chunk text in DB)
  - compute_span_alignment (character-offset span location)
  - citation-to-section-slice validation
"""
import uuid

from app.discussion.agents import (
    parse_citations,
    verify_citations,
    normalize_text,
)
from app.db.models import Chunk


# =========================================================================
# parse_citations  (regex parser)
# =========================================================================


class TestParseCitations:
    """Test the regex-based citation parser that extracts
    [cite: chunk_id, "quoted text"] markers from agent output."""

    def test_parse_single_citation(self):
        text = (
            'The author uses imagery effectively '
            '[cite: chunk-123, "The morning sun cast shadows"].'
        )
        clean, citations = parse_citations(text)
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "chunk-123"
        assert citations[0]["text"] == "The morning sun cast shadows"
        # Citation marker should be removed from clean text but quoted text preserved
        assert "[cite:" not in clean

    def test_parse_multiple_citations(self):
        text = (
            'Notice the contrast [cite: c1, "morning sun"] '
            'versus [cite: c2, "evening shadows"].'
        )
        clean, citations = parse_citations(text)
        assert len(citations) == 2
        assert citations[0]["chunk_id"] == "c1"
        assert citations[0]["text"] == "morning sun"
        assert citations[1]["chunk_id"] == "c2"
        assert citations[1]["text"] == "evening shadows"

    def test_parse_no_citations(self):
        text = "This is a response with no citations at all."
        clean, citations = parse_citations(text)
        assert len(citations) == 0
        assert clean == text

    def test_parse_citation_with_uuid_chunk_id(self):
        cid = str(uuid.uuid4())
        text = f'Example [cite: {cid}, "river flows"].'
        clean, citations = parse_citations(text)
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == cid

    def test_clean_text_preserves_quoted_text(self):
        """The regex substitution replaces [cite: id, "text"] with "text",
        so the quoted content remains visible in the cleaned output."""
        text = '[cite: chunk-1, "the river flows"]'
        clean, citations = parse_citations(text)
        assert "the river flows" in clean

    def test_parse_citation_whitespace_variations(self):
        """Whitespace around the chunk_id should be stripped."""
        text = '[cite:   spaced-id  , "some text"]'
        clean, citations = parse_citations(text)
        assert len(citations) == 1
        assert citations[0]["chunk_id"] == "spaced-id"

    def test_parse_citation_adjacent_to_punctuation(self):
        text = 'End of sentence[cite: c1, "quote"].'
        clean, citations = parse_citations(text)
        assert len(citations) == 1
        # The cleaned text should end with the quote and then period
        assert clean.endswith('"quote".')

    def test_parse_citation_empty_quote(self):
        """An empty-quote citation should not match the regex."""
        text = '[cite: c1, ""]'
        _, citations = parse_citations(text)
        # The regex requires at least one char inside quotes: [^"]+
        assert len(citations) == 0

    def test_multiple_citations_same_chunk(self):
        text = (
            '[cite: c1, "first quote"] and [cite: c1, "second quote"]'
        )
        _, citations = parse_citations(text)
        assert len(citations) == 2
        assert citations[0]["chunk_id"] == citations[1]["chunk_id"]
        assert citations[0]["text"] != citations[1]["text"]


# =========================================================================
# normalize_text
# =========================================================================


class TestNormalizeText:
    """Test text normalization used in citation comparison."""

    def test_lowercase(self):
        assert normalize_text("HELLO World") == "hello world"

    def test_collapse_whitespace(self):
        result = normalize_text("hello   world\n\ntest")
        assert result == "hello world test"

    def test_strip_leading_trailing(self):
        assert normalize_text("  padded  ") == "padded"

    def test_unicode_normalization(self):
        # NFKC normalization should make equivalent forms match
        import unicodedata
        text_nfd = unicodedata.normalize("NFD", "caf\u00e9")
        text_nfc = unicodedata.normalize("NFC", "caf\u00e9")
        assert normalize_text(text_nfd) == normalize_text(text_nfc)

    def test_tabs_and_newlines(self):
        assert normalize_text("a\tb\nc") == "a b c"

    def test_empty_string(self):
        assert normalize_text("") == ""


# =========================================================================
# verify_citations
# =========================================================================


class TestVerifyCitations:
    """Test citation verification against actual chunk text in the DB."""

    def test_verify_exact_match(self, mock_db, sample_citations):
        verified, invalid = verify_citations(mock_db, sample_citations["valid_exact"])
        assert len(verified) == 2
        assert len(invalid) == 0
        for v in verified:
            assert v["verified"] is True
            assert v["match_type"] == "exact"

    def test_verify_substring_match(self, mock_db, sample_citations):
        """A quote that is an exact substring of the chunk text
        should be verified as exact."""
        verified, invalid = verify_citations(mock_db, sample_citations["valid_fuzzy"])
        assert len(verified) == 1
        assert len(invalid) == 0
        # The quote is an exact (normalized) substring, so match_type == exact
        assert verified[0]["match_type"] == "exact"

    def test_reject_wrong_chunk(self, mock_db, sample_citations):
        """A quote that exists in the book but is cited against the
        wrong chunk should be rejected."""
        verified, invalid = verify_citations(
            mock_db, sample_citations["invalid_wrong_chunk"]
        )
        assert len(invalid) >= 1

    def test_reject_hallucinated_quote(self, mock_db, sample_citations):
        """A completely fabricated quote should be rejected."""
        verified, invalid = verify_citations(
            mock_db, sample_citations["invalid_hallucinated"]
        )
        assert len(invalid) == 1
        assert invalid[0]["verified"] is False

    def test_reject_missing_chunk(self, mock_db, sample_citations):
        """A citation referencing a non-existent chunk ID should fail
        with a 'not found' reason."""
        verified, invalid = verify_citations(
            mock_db, sample_citations["invalid_missing_chunk"]
        )
        assert len(invalid) == 1
        assert "not found" in invalid[0].get("reason", "").lower()

    def test_empty_citations_list(self, mock_db):
        verified, invalid = verify_citations(mock_db, [])
        assert len(verified) == 0
        assert len(invalid) == 0

    def test_missing_chunk_id_field(self, mock_db):
        """A citation dict without chunk_id should be flagged invalid."""
        citations = [{"text": "something"}]
        verified, invalid = verify_citations(mock_db, citations)
        assert len(invalid) == 1
        assert "missing" in invalid[0]["reason"].lower()

    def test_missing_text_field(self, mock_db, sample_book):
        """A citation dict without text/quote should be flagged invalid."""
        citations = [{"chunk_id": sample_book["chunks"][0].id}]
        verified, invalid = verify_citations(mock_db, citations)
        assert len(invalid) == 1

    def test_verify_case_insensitive(self, mock_db, sample_book):
        """Verification should work regardless of case differences.

        The code uses compute_span_alignment which returns 'normalized'
        when the quote is found after unicode/case normalization."""
        chunk = sample_book["chunks"][0]
        citations = [
            {
                "chunk_id": chunk.id,
                "text": "THE MORNING SUN CAST LONG SHADOWS ACROSS THE EMPTY COURTYARD",
            }
        ]
        verified, invalid = verify_citations(mock_db, citations)
        assert len(verified) == 1
        assert verified[0]["match_type"] in ("exact", "normalized")

    def test_verify_with_extra_whitespace(self, mock_db, sample_book):
        """Normalization should collapse whitespace so the quote still matches."""
        chunk = sample_book["chunks"][0]
        citations = [
            {
                "chunk_id": chunk.id,
                "text": "The   morning  sun   cast   long   shadows",
            }
        ]
        verified, invalid = verify_citations(mock_db, citations)
        assert len(verified) == 1

    def test_high_overlap_reports_near_match_not_verified(self, mock_db, sample_book):
        """High word-set overlap without a contiguous span should be flagged
        as near_match but NOT marked verified. Word-set overlap is too weak
        a signal to trust as grounding — fabricated paraphrase can hit 80%
        without quoting anything.
        """
        chunk = sample_book["chunks"][2]
        citations = [
            {
                "chunk_id": chunk.id,
                "text": "the river wound through the valley like a silver waters carrying stories NONEXISTENT1 NONEXISTENT2",
            }
        ]
        verified, invalid = verify_citations(mock_db, citations)
        # Must never land in verified — only exact/normalized may do so.
        assert verified == []
        # If overlap crossed the (tight) threshold it comes back as near_match.
        if invalid and invalid[0].get("match_type") == "near_match":
            assert invalid[0]["verified"] is False
            assert invalid[0].get("match_score", 0) >= 0.95

    def test_reject_chunk_outside_allowed_slice(self, mock_db, sample_book):
        """A valid quote should still fail if the chunk is outside the session slice."""
        book = sample_book["book"]
        allowed_section = sample_book["section"]

        other_section = __import__(
            "app.db.models", fromlist=["Section"]
        ).Section(
            id=str(uuid.uuid4()),
            book_id=book.id,
            title="Chapter 2: Elsewhere",
            section_type="chapter",
            order_index=1,
            char_start=500,
            char_end=1000,
        )
        mock_db.add(other_section)
        mock_db.flush()

        other_chunk = Chunk(
            id=str(uuid.uuid4()),
            book_id=book.id,
            section_id=other_section.id,
            order_index=0,
            text="This spoiler quote lives outside the active session slice.",
            char_start=500,
            char_end=560,
            token_count=10,
        )
        mock_db.add(other_chunk)
        mock_db.commit()

        allowed_chunk_ids = [
            chunk.id
            for chunk in mock_db.query(Chunk).filter(Chunk.section_id == allowed_section.id).all()
        ]
        verified, invalid = verify_citations(
            mock_db,
            [{"chunk_id": other_chunk.id, "text": "This spoiler quote lives outside"}],
            allowed_chunk_ids=allowed_chunk_ids,
        )
        assert verified == []
        assert len(invalid) == 1
        assert invalid[0]["reason"] == "chunk outside session slice"


# =========================================================================
# Span alignment (compute_span_alignment-like logic)
# =========================================================================


class TestSpanAlignment:
    """Test finding the character offsets of a quote within chunk text.

    The real function may not be exposed yet -- these tests verify the
    algorithm using a local helper that mirrors the intended behaviour.
    """

    @staticmethod
    def _find_span(chunk_text: str, quote: str):
        """Simple span finder: returns (start, end) or None."""
        norm_chunk = normalize_text(chunk_text)
        norm_quote = normalize_text(quote)
        idx = norm_chunk.find(norm_quote)
        if idx == -1:
            return None
        return (idx, idx + len(norm_quote))

    def test_exact_span(self):
        chunk_text = "The morning sun cast long shadows across the empty courtyard."
        quote = "long shadows across"
        result = self._find_span(chunk_text, quote)
        assert result is not None
        start, end = result
        # Verify the span extracts the expected text from the normalized chunk
        norm = normalize_text(chunk_text)
        assert norm[start:end] == normalize_text(quote)

    def test_span_at_beginning(self):
        chunk_text = "The morning sun cast long shadows."
        quote = "the morning sun"
        result = self._find_span(chunk_text, quote)
        assert result is not None
        assert result[0] == 0

    def test_span_at_end(self):
        chunk_text = "The morning sun cast long shadows."
        quote = "long shadows."
        result = self._find_span(chunk_text, quote)
        assert result is not None
        norm = normalize_text(chunk_text)
        assert result[1] == len(norm)

    def test_no_match_returns_none(self):
        chunk_text = "The morning sun cast long shadows."
        quote = "This text is not in the chunk at all."
        result = self._find_span(chunk_text, quote)
        assert result is None

    def test_span_with_extra_whitespace(self):
        chunk_text = "The  morning   sun cast long shadows."
        quote = "morning sun cast"
        result = self._find_span(chunk_text, quote)
        assert result is not None


# =========================================================================
# Citation-to-slice validation
# =========================================================================


class TestCitationSliceValidation:
    """Verify that cited chunks belong to the session's section slice."""

    def test_citation_chunk_belongs_to_session_sections(
        self, mock_db, sample_book
    ):
        """Every chunk created in sample_book belongs to its one section."""
        chunks = sample_book["chunks"]
        section = sample_book["section"]

        for chunk in chunks:
            db_chunk = mock_db.query(Chunk).filter(Chunk.id == chunk.id).first()
            assert db_chunk is not None
            assert db_chunk.section_id == section.id

    def test_citation_chunk_outside_session_slice(
        self, mock_db, sample_book
    ):
        """A chunk from a different section should be identifiable as
        outside the session slice."""
        book = sample_book["book"]

        # Create a second section with its own chunk
        other_section = __import__(
            "app.db.models", fromlist=["Section"]
        ).Section(
            id=str(uuid.uuid4()),
            book_id=book.id,
            title="Chapter 2: The Middle",
            section_type="chapter",
            order_index=1,
            char_start=500,
            char_end=1000,
        )
        mock_db.add(other_section)
        mock_db.flush()

        other_chunk = Chunk(
            id=str(uuid.uuid4()),
            book_id=book.id,
            section_id=other_section.id,
            order_index=0,
            text="This belongs to chapter 2.",
            char_start=500,
            char_end=600,
            token_count=6,
        )
        mock_db.add(other_chunk)
        mock_db.commit()

        session_section_ids = {sample_book["section"].id}
        db_chunk = mock_db.query(Chunk).filter(Chunk.id == other_chunk.id).first()
        assert db_chunk.section_id not in session_section_ids


# =========================================================================
# parse_and_verify_citations (integration of parse + verify)
# =========================================================================


class TestParseAndVerifyCitations:
    """Integration test for the combined parse-then-verify flow."""

    def test_roundtrip_valid(self, mock_db, sample_book):
        from app.discussion.agents import parse_and_verify_citations

        chunk = sample_book["chunks"][0]
        text = (
            f'Good imagery [cite: {chunk.id}, '
            f'"The morning sun cast long shadows across the empty courtyard"].'
        )
        clean, all_cit, invalid = parse_and_verify_citations(mock_db, text)
        assert len(invalid) == 0
        assert "[cite:" not in clean
        assert len(all_cit) == 1
        assert all_cit[0].get("verified") is True

    def test_roundtrip_invalid(self, mock_db, sample_book):
        from app.discussion.agents import parse_and_verify_citations

        chunk = sample_book["chunks"][0]
        text = f'Bad cite [cite: {chunk.id}, "totally made up nonsense that is not anywhere in any chunk"].'
        clean, all_cit, invalid = parse_and_verify_citations(mock_db, text)
        assert len(invalid) >= 1

    def test_strict_mode_drops_invalid(self, mock_db, sample_book):
        from app.discussion.agents import parse_and_verify_citations

        chunk = sample_book["chunks"][0]
        text = f'Bad [cite: {chunk.id}, "totally fabricated text not in the corpus at all for real"].'
        clean, verified_only, invalid = parse_and_verify_citations(
            mock_db, text, strict=True
        )
        # In strict mode, verified_only should contain only verified citations
        for c in verified_only:
            assert c.get("verified") is True
