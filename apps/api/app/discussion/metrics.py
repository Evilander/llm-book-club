"""Metrics tracking for discussion pipeline stages."""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class CitationMetrics:
    """Metrics for citation verification quality on a single agent message."""
    attempted: int = 0
    verified: int = 0
    invalid: int = 0
    repair_attempted: bool = False
    repair_succeeded: bool = False
    # Counts after repair (only set if repair was attempted)
    post_repair_verified: int = 0
    post_repair_invalid: int = 0
    # Breakdown by match type (exact / normalized / fuzzy)
    match_type_counts: dict[str, int] = field(default_factory=dict)
    # List of reasons for invalid citations (e.g. "chunk not found", "quote not found in chunk")
    invalid_reasons: list[str] = field(default_factory=list)

    @property
    def verification_rate(self) -> float:
        """Fraction of attempted citations that were verified (0.0-1.0)."""
        return self.verified / self.attempted if self.attempted > 0 else 0.0

    @property
    def repair_rate(self) -> float:
        """Fraction of invalid citations fixed by repair (0.0-1.0)."""
        if not self.repair_attempted or self.invalid == 0:
            return 0.0
        fixed = self.invalid - self.post_repair_invalid
        return fixed / self.invalid if self.invalid > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "verified": self.verified,
            "invalid": self.invalid,
            "verification_rate": round(self.verification_rate, 3),
            "repair_attempted": self.repair_attempted,
            "repair_succeeded": self.repair_succeeded,
            "repair_rate": round(self.repair_rate, 3),
            "post_repair_verified": self.post_repair_verified,
            "post_repair_invalid": self.post_repair_invalid,
            "match_type_counts": self.match_type_counts,
            "invalid_reasons": self.invalid_reasons,
        }

    def log_summary(self, agent_id: str) -> None:
        """Emit a structured log line summarising citation quality."""
        rate = self.verification_rate
        level = logging.WARNING if rate < 0.5 and self.attempted > 0 else logging.INFO
        logger.log(
            level,
            "[CitationMetrics] agent=%s attempted=%d verified=%d invalid=%d "
            "rate=%.1f%% match_types=%s repair_attempted=%s repair_rate=%.1f%%",
            agent_id,
            self.attempted,
            self.verified,
            self.invalid,
            rate * 100,
            self.match_type_counts,
            self.repair_attempted,
            self.repair_rate * 100,
        )


def build_citation_metrics(
    verified: list[dict],
    invalid: list[dict],
    *,
    repair_attempted: bool = False,
    repair_succeeded: bool = False,
    post_repair_verified: int = 0,
    post_repair_invalid: int = 0,
) -> CitationMetrics:
    """
    Build a CitationMetrics from the verified / invalid lists produced by
    ``verify_citations()``.
    """
    # Count match types from verified citations
    match_type_counts: dict[str, int] = {}
    for c in verified:
        mt = c.get("match_type") or "unknown"
        match_type_counts[mt] = match_type_counts.get(mt, 0) + 1

    # Collect invalid reasons
    invalid_reasons: list[str] = []
    for c in invalid:
        reason = c.get("reason", "unknown")
        invalid_reasons.append(reason)

    return CitationMetrics(
        attempted=len(verified) + len(invalid),
        verified=len(verified),
        invalid=len(invalid),
        repair_attempted=repair_attempted,
        repair_succeeded=repair_succeeded,
        post_repair_verified=post_repair_verified,
        post_repair_invalid=post_repair_invalid,
        match_type_counts=match_type_counts,
        invalid_reasons=invalid_reasons,
    )


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage."""
    stage: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "duration_ms": round(self.duration_ms, 2),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


@dataclass
class TurnMetrics:
    """Metrics for a complete discussion turn."""
    turn_id: str = ""
    stages: list[StageMetrics] = field(default_factory=list)
    total_start: float = 0.0
    total_end: float = 0.0
    ttft_ms: float = 0.0  # Time to first token
    total_ms: float = 0.0

    def start(self):
        self.total_start = time.perf_counter()

    def finish(self):
        self.total_end = time.perf_counter()
        self.total_ms = (self.total_end - self.total_start) * 1000

    def record_ttft(self):
        """Call when the first token is generated."""
        if self.ttft_ms == 0 and self.total_start > 0:
            self.ttft_ms = (time.perf_counter() - self.total_start) * 1000

    @contextmanager
    def track_stage(self, stage_name: str):
        """Context manager to track a pipeline stage."""
        metrics = StageMetrics(stage=stage_name)
        metrics.start_time = time.perf_counter()
        try:
            yield metrics
        finally:
            metrics.end_time = time.perf_counter()
            metrics.duration_ms = (metrics.end_time - metrics.start_time) * 1000
            self.stages.append(metrics)
            logger.info(
                f"[Metrics] {stage_name}: {metrics.duration_ms:.1f}ms"
                f"{f' ({metrics.tokens_out} tokens out)' if metrics.tokens_out else ''}"
            )

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "total_ms": round(self.total_ms, 2),
            "ttft_ms": round(self.ttft_ms, 2),
            "stages": [s.to_dict() for s in self.stages],
        }

    def check_budgets(self) -> list[str]:
        """Check if metrics exceed budgets. Returns list of violations."""
        violations = []
        if self.ttft_ms > 1000:
            violations.append(f"TTFT {self.ttft_ms:.0f}ms > 1000ms budget")
        if self.total_ms > 15000:
            violations.append(f"Total {self.total_ms:.0f}ms > 15000ms budget")
        for stage in self.stages:
            if stage.stage == "reranking" and stage.duration_ms > 500:
                violations.append(f"Reranking {stage.duration_ms:.0f}ms > 500ms budget")
        if violations:
            logger.warning(f"[Metrics] Budget violations: {violations}")
        return violations
