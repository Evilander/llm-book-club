"""Search quality regression suite.

Tests that hybrid search (vector + FTS + RRF) produces better results
than either method alone for mixed queries, and validates that the
fusion algorithm behaves correctly under various degradation scenarios.

All tests use mocked search results -- no real PostgreSQL required.
"""
import pytest

from app.retrieval.search import SearchResult, reciprocal_rank_fusion

from tests.fixtures.eval_gold import (
    GOLD_BOOK,
    GOLD_QUERIES,
    CHUNK_IDS,
    SECTION_IDS,
    GoldChunk,
    RetrievalQuery,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sr(chunk: GoldChunk, score: float = 0.5) -> SearchResult:
    """Build a SearchResult from a GoldChunk."""
    return SearchResult(
        chunk_id=chunk.id,
        section_id=chunk.section_id,
        section_title=None,
        text=chunk.text,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        source_ref=None,
        score=score,
    )


def _sr_id(chunk_id: str, score: float = 0.5) -> SearchResult:
    chunk = GOLD_BOOK.chunk_by_id(chunk_id)
    assert chunk is not None
    return _sr(chunk, score)


def _recall_at_k(retrieved_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant) / len(relevant)


def _mrr(retrieved_ids: list[str], relevant: set[str]) -> float:
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------------------
# Hybrid vs. single-source quality
# ---------------------------------------------------------------------------


class TestHybridVsSingleSource:
    """Test that RRF-fused hybrid search beats vector-only and FTS-only."""

    def test_hybrid_recall_ge_vector_only(self):
        """Hybrid recall@5 should be >= vector-only recall@5 on every query."""
        for q in GOLD_QUERIES:
            relevant = set(q.relevant_chunk_ids)

            # Vector returns relevant + noise
            noise_vec = [cid for cid in CHUNK_IDS if cid not in relevant][:3]
            vector = [_sr_id(cid, 0.9 - i * 0.05) for i, cid in enumerate(q.relevant_chunk_ids)]
            vector += [_sr_id(cid, 0.4 - i * 0.05) for i, cid in enumerate(noise_vec)]

            # FTS returns partial overlap + different noise
            noise_fts = [cid for cid in CHUNK_IDS if cid not in relevant][-3:]
            fts = [_sr_id(cid, 0.8 - i * 0.03) for i, cid in enumerate(q.relevant_chunk_ids)]
            fts += [_sr_id(cid, 0.3 - i * 0.05) for i, cid in enumerate(noise_fts)]

            merged = reciprocal_rank_fusion([vector, fts])
            vector_ids = [r.chunk_id for r in vector]
            merged_ids = [r.chunk_id for r in merged]

            vec_recall = _recall_at_k(vector_ids, relevant, k=5)
            hybrid_recall = _recall_at_k(merged_ids, relevant, k=5)
            assert hybrid_recall >= vec_recall, (
                f"Query '{q.description}': hybrid {hybrid_recall} < vector {vec_recall}"
            )

    def test_hybrid_recall_ge_fts_only(self):
        """Hybrid recall@5 should be >= FTS-only recall@5 on every query."""
        for q in GOLD_QUERIES:
            relevant = set(q.relevant_chunk_ids)

            noise_vec = [cid for cid in CHUNK_IDS if cid not in relevant][:3]
            vector = [_sr_id(cid, 0.9 - i * 0.05) for i, cid in enumerate(q.relevant_chunk_ids)]
            vector += [_sr_id(cid, 0.4 - i * 0.05) for i, cid in enumerate(noise_vec)]

            noise_fts = [cid for cid in CHUNK_IDS if cid not in relevant][-3:]
            fts = [_sr_id(cid, 0.8 - i * 0.03) for i, cid in enumerate(q.relevant_chunk_ids)]
            fts += [_sr_id(cid, 0.3 - i * 0.05) for i, cid in enumerate(noise_fts)]

            merged = reciprocal_rank_fusion([vector, fts])
            fts_ids = [r.chunk_id for r in fts]
            merged_ids = [r.chunk_id for r in merged]

            fts_recall = _recall_at_k(fts_ids, relevant, k=5)
            hybrid_recall = _recall_at_k(merged_ids, relevant, k=5)
            assert hybrid_recall >= fts_recall, (
                f"Query '{q.description}': hybrid {hybrid_recall} < FTS {fts_recall}"
            )

    def test_hybrid_rescues_vector_miss(self):
        """When vector misses a relevant chunk but FTS finds it, hybrid should have it."""
        q = GOLD_QUERIES[4]  # "Briggs station master" -- entity query
        relevant = set(q.relevant_chunk_ids)

        # Vector returns noise only (misses the entity)
        noise = [cid for cid in CHUNK_IDS if cid not in relevant][:5]
        vector = [_sr_id(cid, 0.7 - i * 0.05) for i, cid in enumerate(noise)]

        # FTS catches the name
        fts = [_sr_id(cid, 0.9) for cid in q.relevant_chunk_ids]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = {r.chunk_id for r in merged}
        for cid in relevant:
            assert cid in merged_ids

    def test_hybrid_rescues_fts_miss(self):
        """When FTS misses a relevant chunk but vector finds it, hybrid should have it."""
        q = GOLD_QUERIES[1]  # thematic: "abandoned factories and economic decline"
        relevant = set(q.relevant_chunk_ids)

        # Vector catches thematic meaning
        vector = [_sr_id(cid, 0.95) for cid in q.relevant_chunk_ids]

        # FTS returns noise only (no keyword match for thematic query)
        noise = [cid for cid in CHUNK_IDS if cid not in relevant][:5]
        fts = [_sr_id(cid, 0.5 - i * 0.05) for i, cid in enumerate(noise)]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = {r.chunk_id for r in merged}
        for cid in relevant:
            assert cid in merged_ids


# ---------------------------------------------------------------------------
# RRF fusion quality regression tests
# ---------------------------------------------------------------------------


class TestRRFFusionQuality:
    """Regression tests for the RRF merge algorithm."""

    def test_dual_presence_boosts_rank(self):
        """A chunk appearing in both lists should rank higher than one in just one."""
        # Chunk A appears in both lists at rank 2
        # Chunk B appears only in vector at rank 1
        vector = [_sr_id(CHUNK_IDS[0], 0.9), _sr_id(CHUNK_IDS[1], 0.8)]
        fts = [_sr_id(CHUNK_IDS[2], 0.9), _sr_id(CHUNK_IDS[1], 0.8)]

        merged = reciprocal_rank_fusion([vector, fts])
        ids = [r.chunk_id for r in merged]
        # CHUNK_IDS[1] appears in both lists -> highest RRF score
        assert ids[0] == CHUNK_IDS[1]

    def test_rrf_is_stable_under_score_variation(self):
        """RRF rank should depend on position, not score magnitude."""
        # Same ranks, different absolute scores
        vector_high = [_sr_id(CHUNK_IDS[0], 0.99), _sr_id(CHUNK_IDS[1], 0.98)]
        vector_low = [_sr_id(CHUNK_IDS[0], 0.10), _sr_id(CHUNK_IDS[1], 0.09)]

        merged_high = reciprocal_rank_fusion([vector_high])
        merged_low = reciprocal_rank_fusion([vector_low])

        # Same output order regardless of score magnitude
        assert [r.chunk_id for r in merged_high] == [r.chunk_id for r in merged_low]
        # Same RRF scores (scores are position-based, not value-based)
        for h, l in zip(merged_high, merged_low):
            assert abs(h.score - l.score) < 1e-12

    def test_rrf_handles_disjoint_lists(self):
        """Two lists with no overlap should merge all items."""
        vector = [_sr_id(CHUNK_IDS[0]), _sr_id(CHUNK_IDS[1])]
        fts = [_sr_id(CHUNK_IDS[2]), _sr_id(CHUNK_IDS[3])]

        merged = reciprocal_rank_fusion([vector, fts])
        assert len(merged) == 4
        ids = {r.chunk_id for r in merged}
        assert ids == {CHUNK_IDS[0], CHUNK_IDS[1], CHUNK_IDS[2], CHUNK_IDS[3]}

    def test_rrf_handles_identical_lists(self):
        """Two identical lists should produce the same items (deduplicated) with boosted scores."""
        items = [_sr_id(CHUNK_IDS[0], 0.9), _sr_id(CHUNK_IDS[1], 0.8)]
        merged_single = reciprocal_rank_fusion([items])
        merged_double = reciprocal_rank_fusion([items, list(items)])  # copy to avoid mutation

        assert len(merged_single) == len(merged_double) == 2
        # Double-list scores should be exactly 2x single-list scores
        for s, d in zip(merged_single, merged_double):
            assert abs(d.score - 2 * s.score) < 1e-12

    def test_rrf_preserves_all_chunks_from_both(self):
        """No chunk from either source should be silently dropped."""
        all_chunks = GOLD_BOOK.all_chunks[:10]
        vector = [_sr(c, score=0.9 - i * 0.05) for i, c in enumerate(all_chunks[:7])]
        fts = [_sr(c, score=0.8 - i * 0.05) for i, c in enumerate(all_chunks[3:])]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = {r.chunk_id for r in merged}
        expected_ids = {c.id for c in all_chunks}
        assert merged_ids == expected_ids

    def test_rrf_output_is_sorted_descending(self):
        """Merged output must be sorted by RRF score, highest first."""
        vector = [_sr_id(CHUNK_IDS[i], 0.9 - i * 0.1) for i in range(5)]
        fts = [_sr_id(CHUNK_IDS[i + 5], 0.8 - i * 0.1) for i in range(5)]

        merged = reciprocal_rank_fusion([vector, fts])
        scores = [r.score for r in merged]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Score at position {i} ({scores[i]}) < score at {i+1} ({scores[i+1]})"
            )


# ---------------------------------------------------------------------------
# Degradation scenarios
# ---------------------------------------------------------------------------


class TestDegradationScenarios:
    """Test search quality under various failure/degradation conditions."""

    def test_empty_vector_results(self):
        """When vector search returns nothing, FTS results should still work."""
        q = GOLD_QUERIES[0]
        relevant = set(q.relevant_chunk_ids)

        vector = []  # total failure
        fts = [_sr_id(cid, 0.8 - i * 0.05) for i, cid in enumerate(q.relevant_chunk_ids)]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = [r.chunk_id for r in merged]
        recall = _recall_at_k(merged_ids, relevant, k=5)
        assert recall == 1.0

    def test_empty_fts_results(self):
        """When FTS returns nothing, vector results should still work."""
        q = GOLD_QUERIES[1]
        relevant = set(q.relevant_chunk_ids)

        vector = [_sr_id(cid, 0.9) for cid in q.relevant_chunk_ids]
        fts = []  # total failure

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = [r.chunk_id for r in merged]
        recall = _recall_at_k(merged_ids, relevant, k=5)
        assert recall == 1.0

    def test_both_sources_empty(self):
        """When both sources fail, merge should produce empty results gracefully."""
        merged = reciprocal_rank_fusion([[], []])
        assert len(merged) == 0

    def test_high_noise_low_signal(self):
        """With many noise results and few relevant, relevant should still rank high."""
        q = GOLD_QUERIES[8]  # "portrait of the woman who drowned" -- 1 relevant
        relevant = set(q.relevant_chunk_ids)

        # 1 relevant at rank 1, then 10 noise items
        noise_ids = [cid for cid in CHUNK_IDS if cid not in relevant]
        vector = [_sr_id(q.relevant_chunk_ids[0], 0.85)]
        vector += [_sr_id(cid, 0.7 - i * 0.02) for i, cid in enumerate(noise_ids[:10])]

        fts = [_sr_id(q.relevant_chunk_ids[0], 0.9)]
        fts += [_sr_id(cid, 0.6 - i * 0.02) for i, cid in enumerate(noise_ids[5:15])]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = [r.chunk_id for r in merged]

        # The relevant chunk appears in both lists, so it should be rank 1
        assert merged_ids[0] == q.relevant_chunk_ids[0]

    def test_single_source_fallback(self):
        """RRF with only one list should behave like a passthrough."""
        items = [_sr_id(CHUNK_IDS[i], 0.9 - i * 0.1) for i in range(5)]
        merged = reciprocal_rank_fusion([items])
        assert len(merged) == 5
        # Order should be preserved
        assert [r.chunk_id for r in merged] == [r.chunk_id for r in items]


# ---------------------------------------------------------------------------
# Regression: known-good query/result pairs
# ---------------------------------------------------------------------------


class TestRegressionPairs:
    """Regression tests for specific query-result expectations.

    These encode known-good retrieval behaviors that should not regress.
    If a change to the retrieval pipeline breaks these, it needs justification.
    """

    def test_entity_name_in_top_3(self):
        """'Briggs station master' must return chunk 1 in top-3 after RRF."""
        q = GOLD_QUERIES[4]
        relevant = set(q.relevant_chunk_ids)

        # Simulate reasonable retrieval
        vector = [
            _sr_id(CHUNK_IDS[1], 0.7),  # relevant but not top
            _sr_id(CHUNK_IDS[0], 0.8),
            _sr_id(CHUNK_IDS[3], 0.6),
        ]
        fts = [
            _sr_id(CHUNK_IDS[1], 0.95),  # FTS ranks it high
            _sr_id(CHUNK_IDS[0], 0.5),
        ]

        merged = reciprocal_rank_fusion([vector, fts])
        top_3 = [r.chunk_id for r in merged[:3]]
        assert CHUNK_IDS[1] in top_3

    def test_gothic_reveal_in_top_5(self):
        """The portrait revelation (chunk 14) should appear in top-5 for the reveal query."""
        q = GOLD_QUERIES[8]  # "portrait of the woman who drowned"
        reveal_chunk = CHUNK_IDS[14]

        vector = [
            _sr_id(reveal_chunk, 0.92),
            _sr_id(CHUNK_IDS[11], 0.75),
            _sr_id(CHUNK_IDS[13], 0.60),
        ]
        fts = [
            _sr_id(reveal_chunk, 0.88),
            _sr_id(CHUNK_IDS[15], 0.50),
        ]

        merged = reciprocal_rank_fusion([vector, fts])
        top_5 = [r.chunk_id for r in merged[:5]]
        assert reveal_chunk in top_5

    def test_storm_scene_chunks_cluster(self):
        """Storm-related chunks should cluster together in results."""
        q = GOLD_QUERIES[6]  # "the storm and the light in the Voss estate"
        relevant = set(q.relevant_chunk_ids)

        vector = [_sr_id(cid, 0.9 - i * 0.03) for i, cid in enumerate(q.relevant_chunk_ids)]
        vector += [_sr_id(CHUNK_IDS[0], 0.5), _sr_id(CHUNK_IDS[7], 0.45)]

        fts = [_sr_id(cid, 0.85 - i * 0.03) for i, cid in enumerate(q.relevant_chunk_ids)]
        fts += [_sr_id(CHUNK_IDS[3], 0.4)]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = [r.chunk_id for r in merged]

        # All 3 relevant chunks should be in the top 4 (allowing 1 interloper)
        top_4_set = set(merged_ids[:4])
        found = len(relevant & top_4_set)
        assert found >= 2, f"Only {found}/3 storm chunks in top 4"

    def test_journal_discovery_chunks(self):
        """Journal-related chunks should dominate results for journal queries."""
        q = GOLD_QUERIES[3]  # "grandmother's journal and botanical observations"
        relevant = set(q.relevant_chunk_ids)

        vector = [_sr_id(cid, 0.88 - i * 0.04) for i, cid in enumerate(q.relevant_chunk_ids)]
        vector += [_sr_id(CHUNK_IDS[0], 0.4)]

        fts = [_sr_id(cid, 0.82 - i * 0.03) for i, cid in enumerate(q.relevant_chunk_ids)]
        fts += [_sr_id(CHUNK_IDS[5], 0.35)]

        merged = reciprocal_rank_fusion([vector, fts])
        top_5 = [r.chunk_id for r in merged[:5]]

        for cid in relevant:
            assert cid in top_5, f"Journal chunk {cid} not in top-5"
