"""Citation verification evaluation suite.

Tests exact match, normalized match, invalid citation rejection,
span alignment accuracy, repair trigger conditions, and citation
metrics correctness -- all using the gold-standard fixtures against
real verify_citations / compute_span_alignment logic with a mock DB.
"""
import uuid

import pytest

from app.discussion.agents import (
    verify_citations,
    compute_span_alignment,
    normalize_text,
)
from app.discussion.metrics import CitationMetrics, build_citation_metrics
from app.db.models import (
    Base,
    Book,
    Section,
    Chunk,
    IngestStatus,
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.fixtures.eval_gold import (
    GOLD_BOOK,
    GOLD_CITATIONS,
    CHUNK_IDS,
    SECTION_IDS,
    CitationTestCase,
    build_citation_test_cases,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gold_db():
    """Create an in-memory SQLite DB populated with the entire gold corpus."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Insert book
    book = Book(
        id=GOLD_BOOK.id,
        title=GOLD_BOOK.title,
        author=GOLD_BOOK.author,
        filename="the_voss_inheritance.epub",
        file_type="epub",
        file_size_bytes=250000,
        ingest_status=IngestStatus.COMPLETED,
    )
    db.add(book)
    db.flush()

    # Insert sections and chunks
    for gs in GOLD_BOOK.sections:
        section = Section(
            id=gs.id,
            book_id=GOLD_BOOK.id,
            title=gs.title,
            section_type=gs.section_type,
            order_index=gs.order_index,
            char_start=gs.char_start,
            char_end=gs.char_end,
        )
        db.add(section)
        db.flush()

        for gc in gs.chunks:
            chunk = Chunk(
                id=gc.id,
                book_id=GOLD_BOOK.id,
                section_id=gs.id,
                order_index=gc.order_index,
                text=gc.text,
                char_start=gc.char_start,
                char_end=gc.char_end,
                token_count=gc.token_count,
            )
            db.add(chunk)

    db.commit()
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_cases(should_verify: bool, match_type: str | None = None) -> list[CitationTestCase]:
    """Filter gold citation test cases."""
    cases = [c for c in GOLD_CITATIONS if c.should_verify == should_verify]
    if match_type is not None:
        cases = [c for c in cases if c.expected_match_type == match_type]
    return cases


# ---------------------------------------------------------------------------
# Exact match verification
# ---------------------------------------------------------------------------


class TestExactMatchVerification:
    """Test that verbatim substring citations are verified as exact."""

    @pytest.mark.parametrize(
        "case",
        _filter_cases(should_verify=True, match_type="exact"),
        ids=lambda c: c.description[:60],
    )
    def test_exact_match_verifies(self, gold_db, case: CitationTestCase):
        citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(verified) == 1, f"Expected verification for: {case.description}"
        assert len(invalid) == 0
        assert verified[0]["verified"] is True
        assert verified[0]["match_type"] == "exact"

    def test_exact_match_has_span_offsets(self, gold_db):
        """Exact matches should produce non-None char_start and char_end."""
        case = _filter_cases(should_verify=True, match_type="exact")[0]
        citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
        verified, _ = verify_citations(gold_db, citations)
        assert verified[0]["char_start"] is not None
        assert verified[0]["char_end"] is not None
        assert verified[0]["char_start"] < verified[0]["char_end"]

    def test_exact_match_span_extracts_correct_text(self, gold_db):
        """The span offsets should point to the original quote in the chunk."""
        case = _filter_cases(should_verify=True, match_type="exact")[0]
        chunk = GOLD_BOOK.chunk_by_id(case.chunk_id)
        assert chunk is not None

        citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
        verified, _ = verify_citations(gold_db, citations)

        start = verified[0]["char_start"]
        end = verified[0]["char_end"]
        extracted = chunk.text[start:end]
        assert extracted == case.quote


# ---------------------------------------------------------------------------
# Normalized match verification
# ---------------------------------------------------------------------------


class TestNormalizedMatchVerification:
    """Test that quotes with case/whitespace differences verify as normalized."""

    @pytest.mark.parametrize(
        "case",
        _filter_cases(should_verify=True, match_type="normalized"),
        ids=lambda c: c.description[:60],
    )
    def test_normalized_match_verifies(self, gold_db, case: CitationTestCase):
        citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(verified) == 1, f"Expected verification for: {case.description}"
        assert verified[0]["verified"] is True
        assert verified[0]["match_type"] in ("exact", "normalized")

    def test_all_caps_normalizes(self, gold_db):
        """ALL-CAPS version of a quote should match via normalization."""
        chunk = GOLD_BOOK.chunk_by_id(CHUNK_IDS[2])
        assert chunk is not None
        all_caps = "THE ONLY INDUSTRY LEFT WAS SILENCE."
        citations = [{"chunk_id": CHUNK_IDS[2], "text": all_caps}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(verified) == 1
        assert verified[0]["match_type"] in ("exact", "normalized")

    def test_extra_whitespace_normalizes(self, gold_db):
        """Extra whitespace between words should not prevent matching."""
        chunk = GOLD_BOOK.chunk_by_id(CHUNK_IDS[5])
        assert chunk is not None
        spaced = "a   narrow   bed,   a   washstand"
        citations = [{"chunk_id": CHUNK_IDS[5], "text": spaced}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(verified) == 1

    def test_normalized_match_has_span_offsets(self, gold_db):
        """Normalized matches should still produce valid span offsets."""
        case = _filter_cases(should_verify=True, match_type="normalized")[0]
        citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
        verified, _ = verify_citations(gold_db, citations)
        assert verified[0]["char_start"] is not None
        assert verified[0]["char_end"] is not None


# ---------------------------------------------------------------------------
# Invalid citation rejection
# ---------------------------------------------------------------------------


class TestInvalidCitationRejection:
    """Test that fabricated, wrong-chunk, and missing-chunk citations are rejected."""

    @pytest.mark.parametrize(
        "case",
        _filter_cases(should_verify=False),
        ids=lambda c: c.description[:60],
    )
    def test_invalid_citation_rejected(self, gold_db, case: CitationTestCase):
        citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(invalid) >= 1, f"Expected rejection for: {case.description}"
        assert invalid[0]["verified"] is False

    def test_wrong_chunk_gives_clear_reason(self, gold_db):
        """A quote from chunk X cited against chunk Y should explain the failure."""
        # "The only industry left was silence." is in chunk 2, cite it against chunk 0
        citations = [{"chunk_id": CHUNK_IDS[0], "text": "The only industry left was silence."}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(invalid) == 1
        assert "not found" in invalid[0]["reason"].lower()

    def test_nonexistent_chunk_id(self, gold_db):
        """A citation with a chunk_id that does not exist should fail with 'not found'."""
        citations = [{"chunk_id": "phantom-chunk-id-XYZ", "text": "any text at all"}]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(invalid) == 1
        assert "not found" in invalid[0]["reason"].lower()

    def test_hallucinated_quote_gives_clear_reason(self, gold_db):
        """Completely fabricated quotes should be flagged with 'not found in chunk'."""
        citations = [{
            "chunk_id": CHUNK_IDS[3],
            "text": "The moonlight painted silver rivers across the desert sand.",
        }]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(invalid) == 1
        assert "not found" in invalid[0]["reason"].lower()

    def test_missing_fields_rejected(self, gold_db):
        """Citations lacking chunk_id or text should be rejected."""
        missing_chunk = [{"text": "some text"}]
        missing_text = [{"chunk_id": CHUNK_IDS[0]}]
        empty_both = [{}]

        for citations in [missing_chunk, missing_text, empty_both]:
            verified, invalid = verify_citations(gold_db, citations)
            assert len(invalid) == 1
            assert "missing" in invalid[0]["reason"].lower()

    def test_chunk_outside_allowed_slice(self, gold_db):
        """A valid citation should fail if chunk is not in allowed_chunk_ids."""
        # Use a quote that IS in chunk 0 but restrict to section 2 chunks only
        section2_chunk_ids = [c.id for c in GOLD_BOOK.sections[1].chunks]
        citations = [{
            "chunk_id": CHUNK_IDS[0],
            "text": "its brakes screaming against the frozen rails",
        }]
        verified, invalid = verify_citations(
            gold_db, citations, allowed_chunk_ids=section2_chunk_ids
        )
        assert len(invalid) == 1
        assert "outside" in invalid[0]["reason"].lower() or "slice" in invalid[0]["reason"].lower()


# ---------------------------------------------------------------------------
# Span alignment correctness
# ---------------------------------------------------------------------------


class TestSpanAlignment:
    """Test compute_span_alignment returns correct character offsets."""

    def test_exact_span_offsets(self):
        """Exact match should return verbatim offsets in original text."""
        chunk_text = GOLD_BOOK.chunk_by_id(CHUNK_IDS[0]).text
        quote = "its brakes screaming against the frozen rails"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        start, end, match_type = result
        assert match_type == "exact"
        assert chunk_text[start:end] == quote

    def test_normalized_span_maps_back_to_original(self):
        """Normalized match should still produce offsets into the original text."""
        chunk_text = GOLD_BOOK.chunk_by_id(CHUNK_IDS[0]).text
        quote = "ELEANOR VOSS STEPPED ONTO THE PLATFORM"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        start, end, match_type = result
        assert match_type == "normalized"
        # The extracted original text should match the quote after normalization
        extracted = chunk_text[start:end]
        assert normalize_text(extracted) == normalize_text(quote)

    def test_span_at_chunk_beginning(self):
        """Quote at the start of the chunk should have char_start = 0."""
        chunk_text = GOLD_BOOK.chunk_by_id(CHUNK_IDS[0]).text
        # First words of chunk 0
        quote = "The train pulled into Ashworth station"
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        assert result[0] == 0

    def test_span_at_chunk_end(self):
        """Quote at the end of the chunk should have char_end = len(chunk)."""
        chunk_text = GOLD_BOOK.chunk_by_id(CHUNK_IDS[2]).text
        quote = "The only industry left was silence."
        result = compute_span_alignment(chunk_text, quote)
        assert result is not None
        assert result[1] == len(chunk_text)

    def test_no_match_returns_none(self):
        """A quote not in the chunk should return None."""
        chunk_text = GOLD_BOOK.chunk_by_id(CHUNK_IDS[0]).text
        result = compute_span_alignment(chunk_text, "This text is not in any chunk whatsoever")
        assert result is None

    def test_empty_inputs(self):
        """Empty chunk or empty quote should return None."""
        assert compute_span_alignment("", "some quote") is None
        assert compute_span_alignment("some text", "") is None
        assert compute_span_alignment("", "") is None

    @pytest.mark.parametrize(
        "chunk_idx",
        range(len(GOLD_BOOK.all_chunks)),
        ids=lambda i: f"chunk_{i}",
    )
    def test_middle_substring_span(self, chunk_idx):
        """A middle substring of each chunk should produce valid span offsets."""
        chunk = GOLD_BOOK.all_chunks[chunk_idx]
        # Extract a 30-char middle substring
        mid = len(chunk.text) // 2
        start = max(0, mid - 15)
        end = min(len(chunk.text), mid + 15)
        quote = chunk.text[start:end]
        if not quote.strip():
            pytest.skip("Empty substring")

        result = compute_span_alignment(chunk.text, quote)
        assert result is not None, f"Failed span alignment for chunk {chunk.id}"
        s, e, mt = result
        assert mt == "exact"
        assert chunk.text[s:e] == quote


# ---------------------------------------------------------------------------
# Repair trigger simulation
# ---------------------------------------------------------------------------


class TestRepairTrigger:
    """Test that the >50% invalid threshold correctly triggers repair logic."""

    def test_repair_threshold_exceeded(self, gold_db):
        """When >50% of citations are invalid, repair should be warranted."""
        # 1 valid + 2 invalid = 66% invalid
        citations = [
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
            {"chunk_id": CHUNK_IDS[0], "text": "fabricated text that does not exist anywhere in the book"},
            {"chunk_id": CHUNK_IDS[0], "text": "another completely made up hallucinated passage of text"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        total = len(verified) + len(invalid)
        invalid_ratio = len(invalid) / total if total > 0 else 0.0
        assert invalid_ratio > 0.5, f"Invalid ratio {invalid_ratio} should exceed 0.5"

    def test_repair_threshold_not_exceeded(self, gold_db):
        """When <=50% invalid, repair should not be triggered."""
        # 2 valid + 1 invalid = 33% invalid
        citations = [
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
            {"chunk_id": CHUNK_IDS[2], "text": "The only industry left was silence."},
            {"chunk_id": CHUNK_IDS[0], "text": "fabricated text not in corpus anywhere at all definitely made up"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        total = len(verified) + len(invalid)
        invalid_ratio = len(invalid) / total if total > 0 else 0.0
        assert invalid_ratio <= 0.5, f"Invalid ratio {invalid_ratio} should not exceed 0.5"

    def test_all_valid_no_repair(self, gold_db):
        """All valid citations should produce 0% invalid -- no repair."""
        exact_cases = _filter_cases(should_verify=True, match_type="exact")
        citations = [{"chunk_id": c.chunk_id, "text": c.quote} for c in exact_cases]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(invalid) == 0
        total = len(verified) + len(invalid)
        assert total == len(exact_cases)

    def test_all_invalid_triggers_repair(self, gold_db):
        """100% invalid citations should definitely warrant repair."""
        citations = [
            {"chunk_id": CHUNK_IDS[3], "text": "hallucination one not in any chunk at all"},
            {"chunk_id": CHUNK_IDS[5], "text": "hallucination two completely fabricated text"},
            {"chunk_id": CHUNK_IDS[7], "text": "hallucination three zero basis in evidence"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        assert len(verified) == 0
        assert len(invalid) == 3


# ---------------------------------------------------------------------------
# Citation metrics accuracy
# ---------------------------------------------------------------------------


class TestCitationMetricsAccuracy:
    """Verify that CitationMetrics counts match actual verify_citations results."""

    def test_metrics_match_verification_counts(self, gold_db):
        """build_citation_metrics should produce counts matching the input lists."""
        citations = [
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
            {"chunk_id": CHUNK_IDS[2], "text": "The only industry left was silence."},
            {"chunk_id": CHUNK_IDS[0], "text": "completely fabricated hallucination not in the book"},
            {"chunk_id": "nonexistent-chunk", "text": "ghost reference"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        metrics = build_citation_metrics(verified, invalid)

        assert metrics.attempted == len(verified) + len(invalid)
        assert metrics.verified == len(verified)
        assert metrics.invalid == len(invalid)

    def test_metrics_match_type_breakdown(self, gold_db):
        """match_type_counts should accurately reflect the verification results."""
        citations = [
            # Exact match
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
            # Normalized match (uppercase)
            {"chunk_id": CHUNK_IDS[2], "text": "THE ONLY INDUSTRY LEFT WAS SILENCE."},
            # Another exact
            {"chunk_id": CHUNK_IDS[17], "text": "The house, it seemed, had been waiting for her."},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        metrics = build_citation_metrics(verified, invalid)

        assert metrics.verified == 3
        assert metrics.invalid == 0
        # Should have both exact and normalized in the type counts
        assert sum(metrics.match_type_counts.values()) == 3
        assert "exact" in metrics.match_type_counts

    def test_metrics_verification_rate(self, gold_db):
        """verification_rate property should match actual ratio."""
        citations = [
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
            {"chunk_id": CHUNK_IDS[0], "text": "made up text that is not in the book at all"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        metrics = build_citation_metrics(verified, invalid)
        expected_rate = len(verified) / (len(verified) + len(invalid))
        assert abs(metrics.verification_rate - expected_rate) < 1e-9

    def test_metrics_invalid_reasons(self, gold_db):
        """invalid_reasons should list the actual rejection reasons."""
        citations = [
            {"chunk_id": "phantom-id", "text": "ghost"},
            {"chunk_id": CHUNK_IDS[0], "text": "text that is not present in this specific chunk whatsoever"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        metrics = build_citation_metrics(verified, invalid)
        assert len(metrics.invalid_reasons) == len(invalid)
        for reason in metrics.invalid_reasons:
            assert isinstance(reason, str)
            assert len(reason) > 0

    def test_metrics_to_dict_roundtrip(self, gold_db):
        """to_dict should produce a serializable dict with all expected keys."""
        citations = [
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
        ]
        verified, invalid = verify_citations(gold_db, citations)
        metrics = build_citation_metrics(verified, invalid)
        d = metrics.to_dict()
        expected_keys = {
            "attempted", "verified", "invalid", "verification_rate",
            "repair_attempted", "repair_succeeded", "repair_rate",
            "post_repair_verified", "post_repair_invalid",
            "match_type_counts", "invalid_reasons",
        }
        assert set(d.keys()) == expected_keys

    def test_metrics_repair_fields_default(self, gold_db):
        """Without repair, repair fields should be default (False, 0)."""
        verified, invalid = verify_citations(gold_db, [
            {"chunk_id": CHUNK_IDS[0], "text": "its brakes screaming against the frozen rails"},
        ])
        metrics = build_citation_metrics(verified, invalid)
        assert metrics.repair_attempted is False
        assert metrics.repair_succeeded is False
        assert metrics.post_repair_verified == 0
        assert metrics.post_repair_invalid == 0
        assert metrics.repair_rate == 0.0

    def test_metrics_repair_fields_set(self, gold_db):
        """When repair info is provided, metrics should reflect it."""
        verified, invalid = verify_citations(gold_db, [
            {"chunk_id": CHUNK_IDS[0], "text": "hallucinated text not in any chunk anywhere"},
            {"chunk_id": CHUNK_IDS[1], "text": "another fabrication with zero textual support"},
        ])
        metrics = build_citation_metrics(
            verified, invalid,
            repair_attempted=True,
            repair_succeeded=True,
            post_repair_verified=2,
            post_repair_invalid=0,
        )
        assert metrics.repair_attempted is True
        assert metrics.repair_succeeded is True
        assert metrics.post_repair_verified == 2
        assert metrics.post_repair_invalid == 0


# ---------------------------------------------------------------------------
# Bulk gold corpus verification
# ---------------------------------------------------------------------------


class TestBulkGoldCorpus:
    """Run all gold citation test cases through verification in bulk."""

    def test_all_valid_cases_verify(self, gold_db):
        """Every gold case marked should_verify=True must pass verification."""
        valid_cases = _filter_cases(should_verify=True)
        assert len(valid_cases) >= 5, "Need sufficient valid test cases"

        for case in valid_cases:
            citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
            verified, invalid = verify_citations(gold_db, citations)
            assert len(verified) == 1, (
                f"FAIL: '{case.description}' -- expected verified, got invalid: "
                f"{invalid}"
            )

    def test_all_invalid_cases_reject(self, gold_db):
        """Every gold case marked should_verify=False must be rejected."""
        invalid_cases = _filter_cases(should_verify=False)
        assert len(invalid_cases) >= 3, "Need sufficient invalid test cases"

        for case in invalid_cases:
            citations = [{"chunk_id": case.chunk_id, "text": case.quote}]
            verified, invalid = verify_citations(gold_db, citations)
            assert len(invalid) >= 1, (
                f"FAIL: '{case.description}' -- expected rejection, got verified: "
                f"{verified}"
            )

    def test_mixed_batch_verification(self, gold_db):
        """Verify a mixed batch of valid and invalid citations at once."""
        all_cases = build_citation_test_cases()
        citations = [{"chunk_id": c.chunk_id, "text": c.quote} for c in all_cases]
        verified, invalid = verify_citations(gold_db, citations)

        expected_valid = sum(1 for c in all_cases if c.should_verify)
        expected_invalid = sum(1 for c in all_cases if not c.should_verify)

        assert len(verified) == expected_valid, (
            f"Expected {expected_valid} verified, got {len(verified)}"
        )
        assert len(invalid) == expected_invalid, (
            f"Expected {expected_invalid} invalid, got {len(invalid)}"
        )
