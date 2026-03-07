"""Tests for retrieval functions: Reciprocal Rank Fusion, search result handling,
and embedding cache logic.

NOTE: vector_search and fts_search require a real Postgres+pgvector database
and are not tested here (they belong in integration tests). These unit tests
cover the pure-Python merge/ranking logic that sits on top of the raw search.
"""
import pytest
import hashlib

from app.retrieval.search import SearchResult, reciprocal_rank_fusion


# =========================================================================
# Helper
# =========================================================================


def _make_result(chunk_id: str, score: float = 0.5, text: str | None = None) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        section_id="s1",
        section_title="Test Section",
        text=text or f"Text for {chunk_id}",
        char_start=0,
        char_end=100,
        source_ref=None,
        score=score,
    )


# =========================================================================
# reciprocal_rank_fusion
# =========================================================================


class TestReciprocalRankFusion:
    """Test the RRF merge algorithm that combines multiple ranked lists."""

    def test_single_list_preserves_order(self):
        results = [_make_result("c1", 0.9), _make_result("c2", 0.7)]
        merged = reciprocal_rank_fusion([results])
        assert len(merged) == 2
        assert merged[0].chunk_id == "c1"
        assert merged[1].chunk_id == "c2"

    def test_merge_two_lists_boosts_shared(self):
        """Items appearing in both lists should rank higher than those
        appearing in only one."""
        list1 = [_make_result("c1"), _make_result("c2"), _make_result("c3")]
        list2 = [_make_result("c2"), _make_result("c3"), _make_result("c4")]
        merged = reciprocal_rank_fusion([list1, list2])
        chunk_ids = [r.chunk_id for r in merged]
        # c2 and c3 appear in both lists, so they get higher RRF score
        assert "c2" in chunk_ids[:2]
        assert "c3" in chunk_ids[:3]

    def test_deduplication(self):
        list1 = [_make_result("c1"), _make_result("c2")]
        list2 = [_make_result("c1"), _make_result("c3")]
        merged = reciprocal_rank_fusion([list1, list2])
        chunk_ids = [r.chunk_id for r in merged]
        # No duplicate chunk IDs
        assert len(set(chunk_ids)) == len(chunk_ids)

    def test_all_empty_lists(self):
        merged = reciprocal_rank_fusion([[], []])
        assert len(merged) == 0

    def test_single_empty_list(self):
        merged = reciprocal_rank_fusion([[]])
        assert len(merged) == 0

    def test_one_empty_one_populated(self):
        list1 = [_make_result("c1"), _make_result("c2")]
        merged = reciprocal_rank_fusion([list1, []])
        assert len(merged) == 2

    def test_k_parameter_affects_scores(self):
        """Different k values should produce different absolute scores
        but the same relative ordering for a single list."""
        list1 = [_make_result("c1"), _make_result("c2")]
        merged_k60 = reciprocal_rank_fusion([list1], k=60)
        merged_k1 = reciprocal_rank_fusion([list1], k=1)
        # Both return same items in same order
        assert merged_k60[0].chunk_id == "c1"
        assert merged_k1[0].chunk_id == "c1"
        # But scores differ
        assert merged_k60[0].score != merged_k1[0].score

    def test_rrf_scores_are_positive(self):
        list1 = [_make_result("c1"), _make_result("c2")]
        list2 = [_make_result("c2"), _make_result("c3")]
        merged = reciprocal_rank_fusion([list1, list2])
        for r in merged:
            assert r.score > 0

    def test_rrf_score_formula(self):
        """Verify the score matches the expected RRF formula:
        score = sum(1 / (k + rank)) for each list."""
        k = 60
        list1 = [_make_result("c1")]  # rank 1 in list1
        list2 = [_make_result("c1")]  # rank 1 in list2
        merged = reciprocal_rank_fusion([list1, list2], k=k)
        expected = 1.0 / (k + 1) + 1.0 / (k + 1)
        assert abs(merged[0].score - expected) < 1e-9

    def test_three_lists(self):
        """RRF should work with more than two lists."""
        list1 = [_make_result("c1"), _make_result("c2")]
        list2 = [_make_result("c2"), _make_result("c3")]
        list3 = [_make_result("c3"), _make_result("c1")]
        merged = reciprocal_rank_fusion([list1, list2, list3])
        chunk_ids = [r.chunk_id for r in merged]
        assert set(chunk_ids) == {"c1", "c2", "c3"}

    def test_preserves_metadata(self):
        """The merged result should carry metadata from the best-ranked copy."""
        r = SearchResult(
            chunk_id="c1",
            section_id="s42",
            section_title="Important Section",
            text="Some important text",
            char_start=10,
            char_end=50,
            source_ref="p.7",
            score=0.95,
        )
        merged = reciprocal_rank_fusion([[r]])
        assert merged[0].section_id == "s42"
        assert merged[0].section_title == "Important Section"
        assert merged[0].text == "Some important text"
        assert merged[0].source_ref == "p.7"

    def test_large_list(self):
        """RRF should handle larger result sets without error."""
        big_list = [_make_result(f"c{i}") for i in range(100)]
        merged = reciprocal_rank_fusion([big_list])
        assert len(merged) == 100
        # First item should have highest score
        assert merged[0].score >= merged[-1].score


# =========================================================================
# SearchResult dataclass
# =========================================================================


class TestSearchResult:
    """Basic tests for the SearchResult dataclass."""

    def test_create(self):
        sr = _make_result("c1", 0.95)
        assert sr.chunk_id == "c1"
        assert sr.score == 0.95

    def test_equality_by_identity(self):
        """Dataclass instances are compared by value by default."""
        sr1 = _make_result("c1", 0.5)
        sr2 = _make_result("c1", 0.5)
        assert sr1 == sr2

    def test_different_scores(self):
        sr1 = _make_result("c1", 0.5)
        sr2 = _make_result("c1", 0.9)
        assert sr1 != sr2


# =========================================================================
# EmbeddingCache (unit test without Redis)
# =========================================================================


class TestEmbeddingCache:
    """Test EmbeddingCache logic without a real Redis instance."""

    def test_cache_key_is_deterministic(self):
        from app.retrieval.cache import EmbeddingCache

        cache = EmbeddingCache("redis://fake:6379/0")
        key1 = cache._cache_key("test query")
        key2 = cache._cache_key("test query")
        assert key1 == key2

    def test_cache_key_differs_for_different_queries(self):
        from app.retrieval.cache import EmbeddingCache

        cache = EmbeddingCache("redis://fake:6379/0")
        key1 = cache._cache_key("query one")
        key2 = cache._cache_key("query two")
        assert key1 != key2

    def test_cache_key_format(self):
        from app.retrieval.cache import EmbeddingCache

        cache = EmbeddingCache("redis://fake:6379/0")
        key = cache._cache_key("hello")
        assert key.startswith("embed_cache:")
        # Should contain a 16-char hex hash
        hash_part = key.split(":")[1]
        assert len(hash_part) == 16
        # Verify it matches the sha256 of the query
        expected_hash = hashlib.sha256("hello".encode()).hexdigest()[:16]
        assert hash_part == expected_hash

    def test_get_returns_none_when_redis_unavailable(self):
        """When Redis is not running, get() should gracefully return None."""
        from app.retrieval.cache import EmbeddingCache

        cache = EmbeddingCache("redis://localhost:1/0")  # unlikely port
        result = cache.get("test")
        assert result is None

    def test_set_does_not_raise_when_redis_unavailable(self):
        """When Redis is not running, set() should not raise."""
        from app.retrieval.cache import EmbeddingCache

        cache = EmbeddingCache("redis://localhost:1/0")
        # Should not raise
        cache.set("test", [0.1, 0.2, 0.3])
