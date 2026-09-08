"""Hybrid search over book chunks: pgvector + PostgreSQL FTS + Reciprocal Rank Fusion + optional reranking."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db import Chunk, Section
from ..providers.embeddings.factory import get_embeddings_client
from .cache import get_embedding_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reranker import (graceful fallback when provider not installed)
# ---------------------------------------------------------------------------
try:
    from ..providers.reranker.factory import get_reranker_client
except ImportError:
    logger.info("Reranker provider not available; reranking will be skipped.")

    def get_reranker_client():  # type: ignore[misc]
        return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A search result with relevance score."""
    chunk_id: str
    section_id: str
    section_title: str | None
    text: str
    char_start: int
    char_end: int
    source_ref: str | None
    score: float  # similarity / relevance score (higher = better)


# ---------------------------------------------------------------------------
# 1. Vector search (pgvector cosine similarity)
# ---------------------------------------------------------------------------

async def vector_search(
    db: Session,
    book_id: str,
    query: str,
    limit: int = 20,
    section_ids: list[str] | None = None,
) -> list[SearchResult]:
    """Semantic search using pgvector cosine similarity.

    Returns up to *limit* candidates ordered by descending cosine similarity.
    """
    t0 = time.perf_counter()

    # Check embedding cache before generating a new embedding
    cache = get_embedding_cache()
    query_embedding = cache.get(query)
    if query_embedding is None:
        embeddings_client = get_embeddings_client()
        query_embedding = await embeddings_client.embed_single(query)
        cache.set(query, query_embedding)

    embedding_str = "[{}]".format(",".join(str(x) for x in query_embedding))

    sql = """
        SELECT
            c.id        AS chunk_id,
            c.section_id,
            s.title     AS section_title,
            c.text,
            c.char_start,
            c.char_end,
            c.source_ref,
            1 - (c.embedding <=> :embedding_vec ::vector) AS score
        FROM chunks c
        JOIN sections s ON c.section_id = s.id
        WHERE c.book_id = :book_id
          AND c.embedding IS NOT NULL
    """

    if section_ids:
        sql += "  AND c.section_id = ANY(:section_ids)\n"

    sql += " ORDER BY c.embedding <=> :embedding_vec ::vector\n LIMIT :limit"

    params: dict = {
        "book_id": book_id,
        "embedding_vec": embedding_str,
        "limit": limit,
    }
    if section_ids:
        params["section_ids"] = section_ids

    result = db.execute(text(sql), params)
    rows = result.fetchall()

    elapsed = time.perf_counter() - t0
    logger.debug("vector_search returned %d results in %.3fs", len(rows), elapsed)

    return [
        SearchResult(
            chunk_id=row.chunk_id,
            section_id=row.section_id,
            section_title=row.section_title,
            text=row.text,
            char_start=row.char_start,
            char_end=row.char_end,
            source_ref=row.source_ref,
            score=float(row.score),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 2. Full-text search (PostgreSQL tsvector / ts_rank)
# ---------------------------------------------------------------------------

def fts_search(
    db: Session,
    book_id: str,
    query: str,
    limit: int = 20,
    section_ids: list[str] | None = None,
) -> list[SearchResult]:
    """BM25-style full-text search using PostgreSQL's built-in tsvector/tsquery.

    Relies on a generated ``text_search`` tsvector column and GIN index on the
    ``chunks`` table (created via Alembic migration).  If the column does not
    exist yet the function returns an empty list so callers degrade gracefully.
    """
    t0 = time.perf_counter()

    sql = """
        SELECT
            c.id        AS chunk_id,
            c.section_id,
            s.title     AS section_title,
            c.text,
            c.char_start,
            c.char_end,
            c.source_ref,
            ts_rank(c.text_search, plainto_tsquery('english', :query)) AS score
        FROM chunks c
        JOIN sections s ON c.section_id = s.id
        WHERE c.book_id = :book_id
          AND c.text_search @@ plainto_tsquery('english', :query)
    """

    if section_ids:
        sql += "  AND c.section_id = ANY(:section_ids)\n"

    sql += " ORDER BY score DESC\n LIMIT :limit"

    params: dict = {"book_id": book_id, "query": query, "limit": limit}
    if section_ids:
        params["section_ids"] = section_ids

    try:
        result = db.execute(text(sql), params)
        rows = result.fetchall()
    except Exception as exc:
        # Most likely the text_search column does not exist yet.
        # CRITICAL: rollback so the session is usable for subsequent queries.
        db.rollback()
        logger.warning(
            "FTS search failed (text_search column may not exist): %s", exc
        )
        return []

    elapsed = time.perf_counter() - t0
    logger.debug("fts_search returned %d results in %.3fs", len(rows), elapsed)

    return [
        SearchResult(
            chunk_id=row.chunk_id,
            section_id=row.section_id,
            section_title=row.section_title,
            text=row.text,
            char_start=row.char_start,
            char_end=row.char_end,
            source_ref=row.source_ref,
            score=float(row.score),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 3. Reciprocal Rank Fusion (RRF)
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    results_lists: list[list[SearchResult]],
    k: int = 60,
) -> list[SearchResult]:
    """Merge multiple ranked result lists via Reciprocal Rank Fusion.

    For every result that appears in one or more lists the RRF score is:

        rrf_score = sum( 1 / (k + rank_i) )  for each list i where the result appears

    ``k`` is a smoothing constant (default 60, standard in the literature).

    Returns a deduplicated list sorted by descending RRF score.
    """
    # Accumulate scores and keep the best SearchResult object per chunk
    rrf_scores: dict[str, float] = defaultdict(float)
    best_result: dict[str, SearchResult] = {}

    for result_list in results_lists:
        for rank, sr in enumerate(result_list, start=1):
            rrf_scores[sr.chunk_id] += 1.0 / (k + rank)
            # Keep the first (highest-ranked) copy we see so metadata is representative
            if sr.chunk_id not in best_result:
                best_result[sr.chunk_id] = sr

    # Build merged list with RRF scores
    merged: list[SearchResult] = []
    for chunk_id, rrf_score in rrf_scores.items():
        sr = best_result[chunk_id]
        merged.append(
            SearchResult(
                chunk_id=sr.chunk_id,
                section_id=sr.section_id,
                section_title=sr.section_title,
                text=sr.text,
                char_start=sr.char_start,
                char_end=sr.char_end,
                source_ref=sr.source_ref,
                score=rrf_score,
            )
        )

    merged.sort(key=lambda r: r.score, reverse=True)
    return merged


# ---------------------------------------------------------------------------
# 4. Hybrid search (vector + FTS + RRF + optional reranking)
# ---------------------------------------------------------------------------

async def hybrid_search(
    db: Session,
    book_id: str,
    query: str,
    limit: int = 5,
    section_ids: list[str] | None = None,
    rerank: bool = True,
) -> list[SearchResult]:
    """Run hybrid search: vector + full-text, merge with RRF, optionally rerank.

    Pipeline:
        1. Run vector search (top-20) and FTS (top-20) concurrently.
        2. Merge results via Reciprocal Rank Fusion.
        3. If *rerank* is ``True`` and a reranker provider is configured, rerank
           the top-30 merged candidates down to *limit*.
        4. Return the top *limit* results.
    """
    t0 = time.perf_counter()
    candidate_k = 20  # candidates per retrieval method

    # --- Step 1: candidate generation -----------------------------------------
    # Run vector search (async) first, then FTS (sync) sequentially.
    # NOTE: fts_search MUST NOT run in a thread pool because it shares the
    # same SQLAlchemy session — cross-thread usage corrupts session state
    # if the FTS query fails (e.g. missing text_search column).
    vector_results = await vector_search(
        db, book_id, query, limit=candidate_k, section_ids=section_ids
    )
    fts_results = fts_search(db, book_id, query, candidate_k, section_ids)

    logger.debug(
        "Candidate generation: %d vector, %d FTS",
        len(vector_results),
        len(fts_results),
    )

    # --- Step 2: merge via RRF ------------------------------------------------
    all_result_lists = [vector_results]
    if fts_results:
        all_result_lists.append(fts_results)

    merged = reciprocal_rank_fusion(all_result_lists)

    # --- Step 3: optional reranking -------------------------------------------
    reranker = None
    if rerank:
        try:
            reranker = get_reranker_client()
        except Exception as exc:
            logger.warning("Failed to instantiate reranker: %s", exc)
            reranker = None

    if reranker is not None:
        rerank_top = 30  # feed top-30 candidates to the reranker
        candidates = merged[:rerank_top]

        if candidates:
            try:
                t_rerank = time.perf_counter()
                rerank_results = await reranker.rerank(
                    query=query,
                    documents=[c.text for c in candidates],
                    top_k=limit,
                )
                elapsed_rerank = time.perf_counter() - t_rerank
                logger.debug(
                    "Reranker returned %d results in %.3fs",
                    len(rerank_results),
                    elapsed_rerank,
                )

                # Map reranker output back to SearchResult objects
                reranked: list[SearchResult] = []
                for rr in rerank_results:
                    sr = candidates[rr.index]
                    reranked.append(
                        SearchResult(
                            chunk_id=sr.chunk_id,
                            section_id=sr.section_id,
                            section_title=sr.section_title,
                            text=sr.text,
                            char_start=sr.char_start,
                            char_end=sr.char_end,
                            source_ref=sr.source_ref,
                            score=float(rr.score),
                        )
                    )
                merged = reranked
            except Exception as exc:
                logger.warning("Reranker failed, falling back to RRF order: %s", exc)
                # Fall through to return top-k from RRF
    else:
        if rerank:
            logger.debug("Reranking requested but no reranker configured; using RRF order.")

    # --- Step 4: trim to requested limit --------------------------------------
    final = merged[:limit]

    elapsed_total = time.perf_counter() - t0
    logger.info(
        "hybrid_search completed: %d results in %.3fs (vector=%d, fts=%d, reranked=%s)",
        len(final),
        elapsed_total,
        len(vector_results),
        len(fts_results),
        reranker is not None,
    )

    return final


# ---------------------------------------------------------------------------
# 5. Public API (backwards-compatible entry point)
# ---------------------------------------------------------------------------

async def search_chunks(
    db: Session,
    book_id: str,
    query: str,
    limit: int = 5,
    section_ids: list[str] | None = None,
) -> list[SearchResult]:
    """Search for relevant chunks using hybrid retrieval (vector + FTS + RRF + reranking).

    This is the primary public API.  All callers that previously used pure
    vector search will transparently benefit from hybrid retrieval.

    Args:
        db: Database session.
        book_id: Book ID to search within.
        query: Search query text.
        limit: Maximum results to return.
        section_ids: Optional filter to specific sections.

    Returns:
        List of :class:`SearchResult` ordered by relevance (best first).
    """
    return await hybrid_search(
        db,
        book_id,
        query,
        limit=limit,
        section_ids=section_ids,
    )


# ---------------------------------------------------------------------------
# 6. Chunk lookup helpers (unchanged)
# ---------------------------------------------------------------------------

def get_chunk_by_id(db: Session, chunk_id: str) -> Chunk | None:
    """Get a specific chunk by ID."""
    return db.query(Chunk).filter(Chunk.id == chunk_id).first()


def get_chunks_by_ids(db: Session, chunk_ids: list[str]) -> list[Chunk]:
    """Get multiple chunks by IDs."""
    return db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
