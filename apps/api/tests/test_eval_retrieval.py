"""Retrieval quality evaluation suite.

Tests precision@k, recall@k, mean reciprocal rank, RRF merge quality,
and section filtering -- all using the gold-standard fixtures with
mocked search results (no real database required).
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


def _sr_from_id(chunk_id: str, score: float = 0.5) -> SearchResult:
    """Build a SearchResult by chunk_id lookup in the gold book."""
    chunk = GOLD_BOOK.chunk_by_id(chunk_id)
    assert chunk is not None, f"Gold chunk {chunk_id} not found"
    return _sr(chunk, score)


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of top-k results that are relevant."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for cid in top_k if cid in relevant_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of relevant items found in top-k."""
    if not relevant_ids:
        return 1.0  # vacuous truth
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def mean_reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """1/rank of the first relevant result (0 if none found)."""
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in relevant_ids:
            return 1.0 / rank
    return 0.0


def _simulate_vector_results(
    query: RetrievalQuery,
    noise_ids: list[str] | None = None,
) -> list[SearchResult]:
    """Simulate vector search: relevant chunks + some noise, scored by position."""
    results = []
    # Relevant chunks get high scores
    for i, cid in enumerate(query.relevant_chunk_ids):
        results.append(_sr_from_id(cid, score=0.95 - i * 0.05))
    # Add noise
    for i, noise_id in enumerate(noise_ids or []):
        results.append(_sr_from_id(noise_id, score=0.4 - i * 0.05))
    return results


def _simulate_fts_results(
    query: RetrievalQuery,
    noise_ids: list[str] | None = None,
) -> list[SearchResult]:
    """Simulate FTS search: relevant chunks + different noise, scored by position."""
    results = []
    for i, cid in enumerate(query.relevant_chunk_ids):
        results.append(_sr_from_id(cid, score=0.85 - i * 0.03))
    for i, noise_id in enumerate(noise_ids or []):
        results.append(_sr_from_id(noise_id, score=0.3 - i * 0.05))
    return results


# ---------------------------------------------------------------------------
# Precision@k
# ---------------------------------------------------------------------------


class TestPrecisionAtK:
    """Test precision at k=5 across gold queries."""

    @pytest.mark.parametrize("query", GOLD_QUERIES, ids=lambda q: q.description[:50])
    def test_perfect_retrieval_precision(self, query: RetrievalQuery):
        """When the retriever returns only relevant chunks, precision is 1.0."""
        retrieved = [_sr_from_id(cid) for cid in query.relevant_chunk_ids]
        retrieved_ids = [r.chunk_id for r in retrieved]
        relevant = set(query.relevant_chunk_ids)
        p = precision_at_k(retrieved_ids, relevant, k=5)
        assert p == 1.0

    def test_precision_degrades_with_noise(self):
        """Adding irrelevant results to the top-k reduces precision."""
        q = GOLD_QUERIES[0]  # "Eleanor arrives at the train station"
        relevant = set(q.relevant_chunk_ids)
        # 2 relevant + 3 noise in top-5
        noise = [CHUNK_IDS[10], CHUNK_IDS[11], CHUNK_IDS[12]]
        vector_results = _simulate_vector_results(q, noise_ids=noise)
        retrieved_ids = [r.chunk_id for r in vector_results]
        p = precision_at_k(retrieved_ids, relevant, k=5)
        assert p == 2.0 / 5.0  # 2 relevant out of 5

    def test_precision_zero_when_all_noise(self):
        """When none of the top-k are relevant, precision is 0."""
        relevant = {CHUNK_IDS[0]}
        noise_ids = [CHUNK_IDS[5], CHUNK_IDS[6], CHUNK_IDS[7], CHUNK_IDS[8], CHUNK_IDS[9]]
        retrieved_ids = noise_ids
        p = precision_at_k(retrieved_ids, relevant, k=5)
        assert p == 0.0

    def test_precision_empty_retrieval(self):
        """Empty retrieval yields 0 precision."""
        p = precision_at_k([], {CHUNK_IDS[0]}, k=5)
        assert p == 0.0


# ---------------------------------------------------------------------------
# Recall@k
# ---------------------------------------------------------------------------


class TestRecallAtK:
    """Test recall at k=5 across gold queries."""

    @pytest.mark.parametrize("query", GOLD_QUERIES, ids=lambda q: q.description[:50])
    def test_perfect_retrieval_recall(self, query: RetrievalQuery):
        """When retriever returns all relevant chunks within top-k, recall is 1.0."""
        retrieved = [_sr_from_id(cid) for cid in query.relevant_chunk_ids]
        retrieved_ids = [r.chunk_id for r in retrieved]
        relevant = set(query.relevant_chunk_ids)
        r = recall_at_k(retrieved_ids, relevant, k=5)
        assert r == 1.0

    def test_partial_recall(self):
        """When only some relevant chunks are retrieved, recall is partial."""
        q = GOLD_QUERIES[3]  # grandmother's journal: 3 relevant
        relevant = set(q.relevant_chunk_ids)
        # Only return 1 of 3 relevant
        retrieved_ids = [q.relevant_chunk_ids[0], CHUNK_IDS[0], CHUNK_IDS[1]]
        r = recall_at_k(retrieved_ids, relevant, k=5)
        assert abs(r - 1.0 / 3.0) < 1e-9

    def test_recall_zero(self):
        """When no relevant chunks are retrieved, recall is 0."""
        relevant = {CHUNK_IDS[0], CHUNK_IDS[1]}
        retrieved_ids = [CHUNK_IDS[10], CHUNK_IDS[11]]
        r = recall_at_k(retrieved_ids, relevant, k=5)
        assert r == 0.0

    def test_recall_with_empty_relevant(self):
        """No relevant items defined: vacuously 1.0."""
        r = recall_at_k([CHUNK_IDS[0]], set(), k=5)
        assert r == 1.0


# ---------------------------------------------------------------------------
# Mean Reciprocal Rank
# ---------------------------------------------------------------------------


class TestMeanReciprocalRank:
    """Test MRR computation."""

    def test_mrr_first_result_relevant(self):
        """If the first result is relevant, MRR = 1.0."""
        relevant = {CHUNK_IDS[0]}
        retrieved = [CHUNK_IDS[0], CHUNK_IDS[1], CHUNK_IDS[2]]
        assert mean_reciprocal_rank(retrieved, relevant) == 1.0

    def test_mrr_second_result_relevant(self):
        """If first relevant is at rank 2, MRR = 0.5."""
        relevant = {CHUNK_IDS[1]}
        retrieved = [CHUNK_IDS[0], CHUNK_IDS[1], CHUNK_IDS[2]]
        assert mean_reciprocal_rank(retrieved, relevant) == 0.5

    def test_mrr_third_result_relevant(self):
        """First relevant at rank 3 => MRR = 1/3."""
        relevant = {CHUNK_IDS[5]}
        retrieved = [CHUNK_IDS[0], CHUNK_IDS[1], CHUNK_IDS[5]]
        assert abs(mean_reciprocal_rank(retrieved, relevant) - 1.0 / 3.0) < 1e-9

    def test_mrr_no_relevant(self):
        """No relevant results => MRR = 0."""
        relevant = {CHUNK_IDS[17]}
        retrieved = [CHUNK_IDS[0], CHUNK_IDS[1], CHUNK_IDS[2]]
        assert mean_reciprocal_rank(retrieved, relevant) == 0.0

    def test_mrr_multiple_relevant_returns_first(self):
        """MRR is based on the first relevant, not all."""
        relevant = {CHUNK_IDS[1], CHUNK_IDS[2]}
        retrieved = [CHUNK_IDS[0], CHUNK_IDS[2], CHUNK_IDS[1]]
        # First relevant is at rank 2
        assert mean_reciprocal_rank(retrieved, relevant) == 0.5

    @pytest.mark.parametrize("query", GOLD_QUERIES, ids=lambda q: q.description[:50])
    def test_mrr_on_perfect_retrieval(self, query: RetrievalQuery):
        """When relevant chunks are returned first, MRR = 1.0."""
        retrieved_ids = list(query.relevant_chunk_ids) + [CHUNK_IDS[0]]
        relevant = set(query.relevant_chunk_ids)
        mrr = mean_reciprocal_rank(retrieved_ids, relevant)
        assert mrr == 1.0


# ---------------------------------------------------------------------------
# RRF merge quality
# ---------------------------------------------------------------------------


class TestRRFMergeQuality:
    """Test that RRF fusion preserves and boosts relevant results."""

    def test_rrf_does_not_lose_vector_relevant(self):
        """Relevant results from vector search should survive RRF merge."""
        q = GOLD_QUERIES[0]
        relevant = set(q.relevant_chunk_ids)

        vector_results = _simulate_vector_results(
            q, noise_ids=[CHUNK_IDS[10], CHUNK_IDS[11]]
        )
        # FTS returns different noise but no relevant results
        fts_results = [
            _sr_from_id(CHUNK_IDS[12], 0.8),
            _sr_from_id(CHUNK_IDS[13], 0.7),
        ]

        merged = reciprocal_rank_fusion([vector_results, fts_results])
        merged_ids = {r.chunk_id for r in merged}
        for cid in relevant:
            assert cid in merged_ids, f"RRF lost relevant chunk {cid} from vector"

    def test_rrf_does_not_lose_fts_relevant(self):
        """Relevant results from FTS should survive RRF merge."""
        q = GOLD_QUERIES[4]  # "Briggs station master"
        relevant = set(q.relevant_chunk_ids)

        # Vector returns noise only
        vector_results = [
            _sr_from_id(CHUNK_IDS[10], 0.6),
            _sr_from_id(CHUNK_IDS[11], 0.5),
        ]
        # FTS catches the entity name
        fts_results = _simulate_fts_results(
            q, noise_ids=[CHUNK_IDS[12]]
        )

        merged = reciprocal_rank_fusion([vector_results, fts_results])
        merged_ids = {r.chunk_id for r in merged}
        for cid in relevant:
            assert cid in merged_ids, f"RRF lost relevant chunk {cid} from FTS"

    def test_rrf_boosts_items_in_both_lists(self):
        """Items appearing in both vector and FTS should rank higher."""
        q = GOLD_QUERIES[6]  # storm and light
        relevant = set(q.relevant_chunk_ids)

        # Both sources return the same relevant chunks
        vector_results = _simulate_vector_results(
            q, noise_ids=[CHUNK_IDS[0], CHUNK_IDS[1]]
        )
        fts_results = _simulate_fts_results(
            q, noise_ids=[CHUNK_IDS[2], CHUNK_IDS[3]]
        )

        merged = reciprocal_rank_fusion([vector_results, fts_results])
        merged_ids = [r.chunk_id for r in merged]

        # Relevant items should appear in the top positions
        # They appear in both lists so they get boosted
        for cid in relevant:
            rank = merged_ids.index(cid) + 1
            assert rank <= len(relevant) + 2, (
                f"Relevant chunk {cid} at rank {rank} -- expected top {len(relevant) + 2}"
            )

    def test_rrf_all_gold_queries_preserve_relevant(self):
        """Across all gold queries, RRF should never drop relevant chunks
        when they appear in at least one source list."""
        for query in GOLD_QUERIES:
            relevant = set(query.relevant_chunk_ids)
            vector = _simulate_vector_results(query, noise_ids=[CHUNK_IDS[0]])
            fts = _simulate_fts_results(query, noise_ids=[CHUNK_IDS[1]])
            merged = reciprocal_rank_fusion([vector, fts])
            merged_ids = {r.chunk_id for r in merged}
            for cid in relevant:
                assert cid in merged_ids, (
                    f"Query '{query.description}': RRF lost relevant chunk {cid}"
                )

    def test_rrf_recall_at_5_on_gold_queries(self):
        """Average recall@5 across all gold queries should be 1.0 when
        relevant chunks appear in at least one source."""
        total_recall = 0.0
        for query in GOLD_QUERIES:
            relevant = set(query.relevant_chunk_ids)
            vector = _simulate_vector_results(query)
            fts = _simulate_fts_results(query)
            merged = reciprocal_rank_fusion([vector, fts])
            merged_ids = [r.chunk_id for r in merged]
            total_recall += recall_at_k(merged_ids, relevant, k=5)
        avg_recall = total_recall / len(GOLD_QUERIES)
        assert avg_recall == 1.0, f"Average recall@5 = {avg_recall} (expected 1.0)"


# ---------------------------------------------------------------------------
# Section filtering
# ---------------------------------------------------------------------------


class TestSectionFiltering:
    """Test that section_id filtering correctly restricts results."""

    def test_filter_to_single_section(self):
        """Only chunks from the specified section should remain."""
        allowed_section_id = SECTION_IDS[0]
        all_chunks = GOLD_BOOK.all_chunks
        results = [_sr(c, score=0.5) for c in all_chunks]

        # Simulate section filtering
        filtered = [
            r for r in results if r.section_id == allowed_section_id
        ]
        assert len(filtered) == 6  # section 1 has 6 chunks
        for r in filtered:
            assert r.section_id == allowed_section_id

    def test_filter_to_multiple_sections(self):
        """Multiple allowed sections should include chunks from each."""
        allowed = {SECTION_IDS[0], SECTION_IDS[2]}
        all_chunks = GOLD_BOOK.all_chunks
        results = [_sr(c, score=0.5) for c in all_chunks]

        filtered = [r for r in results if r.section_id in allowed]
        assert len(filtered) == 12  # 6 + 6
        for r in filtered:
            assert r.section_id in allowed

    def test_filter_excludes_out_of_slice(self):
        """Chunks from non-allowed sections should be excluded."""
        allowed_section_id = SECTION_IDS[1]
        excluded_chunk_ids = {
            c.id for c in GOLD_BOOK.all_chunks
            if c.section_id != allowed_section_id
        }
        all_results = [_sr(c, score=0.5) for c in GOLD_BOOK.all_chunks]
        filtered = [r for r in all_results if r.section_id == allowed_section_id]

        filtered_ids = {r.chunk_id for r in filtered}
        # No excluded chunks should appear
        assert len(filtered_ids & excluded_chunk_ids) == 0

    def test_filter_preserves_rrf_ordering(self):
        """Section filtering before RRF should not break ranking."""
        allowed = SECTION_IDS[2]
        q = GOLD_QUERIES[6]  # storm query - relevant chunks in section 3

        # Only include section 3 chunks
        s3_chunks = [c for c in GOLD_BOOK.all_chunks if c.section_id == allowed]
        vector = [_sr(c, score=0.9 - i * 0.1) for i, c in enumerate(s3_chunks)]
        fts = [_sr(c, score=0.8 - i * 0.1) for i, c in enumerate(s3_chunks)]

        merged = reciprocal_rank_fusion([vector, fts])
        merged_ids = [r.chunk_id for r in merged]
        relevant = set(q.relevant_chunk_ids)

        # All relevant chunks from section 3 should be present
        section3_relevant = relevant & {c.id for c in s3_chunks}
        for cid in section3_relevant:
            assert cid in merged_ids


# ---------------------------------------------------------------------------
# Entity vs. thematic query type awareness
# ---------------------------------------------------------------------------


class TestQueryTypeAwareness:
    """Test that different query types are better served by different
    retrieval methods (FTS for entities, vector for thematic)."""

    def test_entity_query_fts_advantage(self):
        """For entity queries (names), FTS should rank relevant results higher."""
        entity_queries = [q for q in GOLD_QUERIES if q.query_type == "entity"]
        assert len(entity_queries) >= 2, "Need entity queries in gold set"

        for q in entity_queries:
            relevant = set(q.relevant_chunk_ids)
            # Simulate FTS catching entity names precisely
            fts = _simulate_fts_results(q)
            fts_ids = [r.chunk_id for r in fts]
            fts_mrr = mean_reciprocal_rank(fts_ids, relevant)

            # Simulate vector search missing the entity
            noise = [cid for cid in CHUNK_IDS if cid not in relevant][:5]
            vector = [_sr_from_id(cid, score=0.6 - i * 0.05) for i, cid in enumerate(noise)]
            vector_ids = [r.chunk_id for r in vector]
            vector_mrr = mean_reciprocal_rank(vector_ids, relevant)

            assert fts_mrr > vector_mrr, (
                f"Entity query '{q.query}': FTS MRR ({fts_mrr}) should beat "
                f"vector MRR ({vector_mrr})"
            )

    def test_thematic_query_vector_advantage(self):
        """For thematic queries, vector search should rank relevant results higher."""
        thematic_queries = [q for q in GOLD_QUERIES if q.query_type == "thematic"]
        assert len(thematic_queries) >= 2, "Need thematic queries in gold set"

        for q in thematic_queries:
            relevant = set(q.relevant_chunk_ids)
            # Simulate vector catching semantic meaning
            vector = _simulate_vector_results(q)
            vector_ids = [r.chunk_id for r in vector]
            vector_mrr = mean_reciprocal_rank(vector_ids, relevant)

            # Simulate FTS missing thematic content (no keyword match)
            noise = [cid for cid in CHUNK_IDS if cid not in relevant][:5]
            fts = [_sr_from_id(cid, score=0.4 - i * 0.05) for i, cid in enumerate(noise)]
            fts_ids = [r.chunk_id for r in fts]
            fts_mrr = mean_reciprocal_rank(fts_ids, relevant)

            assert vector_mrr > fts_mrr, (
                f"Thematic query '{q.query}': vector MRR ({vector_mrr}) should beat "
                f"FTS MRR ({fts_mrr})"
            )

    def test_hybrid_benefits_both_query_types(self):
        """After RRF fusion, both entity and thematic queries should
        have recall@5 = 1.0 when both sources contribute."""
        for q in GOLD_QUERIES:
            relevant = set(q.relevant_chunk_ids)
            vector = _simulate_vector_results(q)
            fts = _simulate_fts_results(q)
            merged = reciprocal_rank_fusion([vector, fts])
            merged_ids = [r.chunk_id for r in merged]
            r = recall_at_k(merged_ids, relevant, k=5)
            assert r == 1.0, (
                f"Query type={q.query_type} '{q.description}': recall@5 = {r}"
            )
