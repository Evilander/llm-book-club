"""Tests for the discussion metrics tracking module.

Covers:
  - CitationMetrics: citation verification quality tracking
  - build_citation_metrics: factory from verified/invalid lists
  - StageMetrics: per-stage timing and token tracking
  - TurnMetrics:  full-turn metrics with TTFT, budget checks
"""
import time

import pytest

from app.discussion.metrics import (
    CitationMetrics,
    build_citation_metrics,
    StageMetrics,
    TurnMetrics,
)


# =========================================================================
# CitationMetrics
# =========================================================================


class TestCitationMetrics:
    """Test citation quality metrics tracking."""

    def test_verification_rate_no_citations(self):
        m = CitationMetrics(attempted=0, verified=0, invalid=0)
        assert m.verification_rate == 0.0

    def test_verification_rate_all_verified(self):
        m = CitationMetrics(attempted=5, verified=5, invalid=0)
        assert m.verification_rate == 1.0

    def test_verification_rate_mixed(self):
        m = CitationMetrics(attempted=4, verified=3, invalid=1)
        assert m.verification_rate == 0.75

    def test_repair_rate_no_repair(self):
        m = CitationMetrics(attempted=3, verified=1, invalid=2, repair_attempted=False)
        assert m.repair_rate == 0.0

    def test_repair_rate_with_repair(self):
        m = CitationMetrics(
            attempted=4,
            verified=1,
            invalid=3,
            repair_attempted=True,
            repair_succeeded=True,
            post_repair_verified=3,
            post_repair_invalid=1,
        )
        # 3 were invalid, post-repair 1 invalid => 2 fixed => rate = 2/3
        assert abs(m.repair_rate - 2 / 3) < 0.001

    def test_to_dict_keys(self):
        m = CitationMetrics(
            attempted=2,
            verified=1,
            invalid=1,
            match_type_counts={"exact": 1},
            invalid_reasons=["quote not found in chunk"],
        )
        d = m.to_dict()
        assert d["attempted"] == 2
        assert d["verified"] == 1
        assert d["invalid"] == 1
        assert d["verification_rate"] == 0.5
        assert d["repair_attempted"] is False
        assert d["match_type_counts"] == {"exact": 1}
        assert d["invalid_reasons"] == ["quote not found in chunk"]

    def test_log_summary_warning_on_low_rate(self, caplog):
        """Low verification rate should log at WARNING level."""
        import logging

        m = CitationMetrics(attempted=4, verified=1, invalid=3)
        with caplog.at_level(logging.WARNING):
            m.log_summary("test_agent")
        assert "[CitationMetrics]" in caplog.text
        assert "test_agent" in caplog.text

    def test_log_summary_info_on_good_rate(self, caplog):
        """High verification rate should log at INFO level."""
        import logging

        m = CitationMetrics(attempted=4, verified=4, invalid=0)
        with caplog.at_level(logging.INFO):
            m.log_summary("test_agent")
        assert "[CitationMetrics]" in caplog.text


class TestBuildCitationMetrics:
    """Test the build_citation_metrics factory function."""

    def test_basic_counts(self):
        verified = [
            {"chunk_id": "a", "text": "hello", "match_type": "exact", "verified": True},
            {"chunk_id": "b", "text": "world", "match_type": "normalized", "verified": True},
        ]
        invalid = [
            {"chunk_id": "c", "text": "oops", "reason": "chunk c not found"},
        ]
        m = build_citation_metrics(verified, invalid)
        assert m.attempted == 3
        assert m.verified == 2
        assert m.invalid == 1
        assert m.match_type_counts == {"exact": 1, "normalized": 1}
        assert m.invalid_reasons == ["chunk c not found"]

    def test_empty_lists(self):
        m = build_citation_metrics([], [])
        assert m.attempted == 0
        assert m.verified == 0
        assert m.invalid == 0
        assert m.match_type_counts == {}
        assert m.invalid_reasons == []

    def test_repair_fields(self):
        m = build_citation_metrics(
            [{"match_type": "exact"}],
            [],
            repair_attempted=True,
            repair_succeeded=True,
            post_repair_verified=3,
            post_repair_invalid=0,
        )
        assert m.repair_attempted is True
        assert m.repair_succeeded is True
        assert m.post_repair_verified == 3
        assert m.post_repair_invalid == 0

    def test_fuzzy_match_type(self):
        verified = [
            {"match_type": "fuzzy"},
            {"match_type": "fuzzy"},
            {"match_type": "exact"},
        ]
        m = build_citation_metrics(verified, [])
        assert m.match_type_counts == {"fuzzy": 2, "exact": 1}

    def test_missing_reason_defaults(self):
        invalid = [{"chunk_id": "x"}]  # no "reason" key
        m = build_citation_metrics([], invalid)
        assert m.invalid_reasons == ["unknown"]


# =========================================================================
# StageMetrics
# =========================================================================


class TestStageMetrics:
    """Test the per-stage metrics dataclass."""

    def test_to_dict(self):
        m = StageMetrics(
            stage="retrieval",
            duration_ms=42.567,
            tokens_in=100,
            tokens_out=50,
        )
        d = m.to_dict()
        assert d["stage"] == "retrieval"
        assert d["duration_ms"] == 42.57  # rounded to 2 decimals
        assert d["tokens_in"] == 100
        assert d["tokens_out"] == 50

    def test_default_values(self):
        m = StageMetrics(stage="test")
        assert m.start_time == 0.0
        assert m.end_time == 0.0
        assert m.duration_ms == 0.0
        assert m.tokens_in == 0
        assert m.tokens_out == 0


# =========================================================================
# TurnMetrics
# =========================================================================


class TestTurnMetrics:
    """Test the full-turn metrics class."""

    def test_start_and_finish(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        # Simulate some work
        time.sleep(0.01)
        m.finish()
        assert m.total_ms > 0
        assert m.total_start > 0
        assert m.total_end > m.total_start

    def test_record_ttft(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        time.sleep(0.01)
        m.record_ttft()
        assert m.ttft_ms > 0

    def test_ttft_only_recorded_once(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        time.sleep(0.01)
        m.record_ttft()
        first_ttft = m.ttft_ms
        time.sleep(0.01)
        m.record_ttft()
        # Second call should not overwrite
        assert m.ttft_ms == first_ttft

    def test_track_stage_context_manager(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        with m.track_stage("retrieval") as stage:
            time.sleep(0.01)
            stage.tokens_out = 42
        assert len(m.stages) == 1
        assert m.stages[0].stage == "retrieval"
        assert m.stages[0].duration_ms > 0
        assert m.stages[0].tokens_out == 42

    def test_multiple_stages(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        with m.track_stage("retrieval"):
            pass
        with m.track_stage("llm_call"):
            pass
        with m.track_stage("citation_verify"):
            pass
        m.finish()
        assert len(m.stages) == 3
        stage_names = [s.stage for s in m.stages]
        assert stage_names == ["retrieval", "llm_call", "citation_verify"]

    def test_to_dict(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        with m.track_stage("test_stage") as s:
            s.tokens_in = 10
            s.tokens_out = 20
        m.finish()
        d = m.to_dict()
        assert d["turn_id"] == "t1"
        assert "total_ms" in d
        assert "ttft_ms" in d
        assert len(d["stages"]) == 1
        assert d["stages"][0]["stage"] == "test_stage"

    def test_check_budgets_no_violations(self):
        m = TurnMetrics(turn_id="t1")
        m.start()
        m.finish()
        m.ttft_ms = 500  # well under 1000ms budget
        m.total_ms = 5000  # well under 15000ms budget
        violations = m.check_budgets()
        assert len(violations) == 0

    def test_check_budgets_ttft_violation(self):
        m = TurnMetrics(turn_id="t1")
        m.ttft_ms = 1500  # exceeds 1000ms budget
        m.total_ms = 5000
        violations = m.check_budgets()
        assert any("TTFT" in v for v in violations)

    def test_check_budgets_total_violation(self):
        m = TurnMetrics(turn_id="t1")
        m.ttft_ms = 500
        m.total_ms = 20000  # exceeds 15000ms budget
        violations = m.check_budgets()
        assert any("Total" in v for v in violations)

    def test_check_budgets_reranking_violation(self):
        m = TurnMetrics(turn_id="t1")
        m.ttft_ms = 500
        m.total_ms = 5000
        m.stages.append(StageMetrics(stage="reranking", duration_ms=600))
        violations = m.check_budgets()
        assert any("Reranking" in v for v in violations)

    def test_check_budgets_multiple_violations(self):
        m = TurnMetrics(turn_id="t1")
        m.ttft_ms = 2000
        m.total_ms = 20000
        m.stages.append(StageMetrics(stage="reranking", duration_ms=1000))
        violations = m.check_budgets()
        assert len(violations) == 3
