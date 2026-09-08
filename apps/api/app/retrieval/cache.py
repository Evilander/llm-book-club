"""Query embedding cache using Redis."""
from __future__ import annotations
import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Cache query embeddings in Redis to avoid redundant API calls."""

    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        self._redis = None
        self._redis_url = redis_url
        self._ttl = ttl_seconds

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis
                self._redis = redis.Redis.from_url(self._redis_url)
                self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed for embedding cache: {e}")
                self._redis = None
        return self._redis

    def _cache_key(self, query: str) -> str:
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"embed_cache:{query_hash}"

    def get(self, query: str) -> Optional[list[float]]:
        """Get cached embedding for a query."""
        r = self._get_redis()
        if r is None:
            return None
        try:
            key = self._cache_key(query)
            data = r.get(key)
            if data:
                logger.debug(f"Embedding cache hit for query: {query[:50]}...")
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Embedding cache get failed: {e}")
        return None

    def set(self, query: str, embedding: list[float]) -> None:
        """Cache an embedding for a query."""
        r = self._get_redis()
        if r is None:
            return
        try:
            key = self._cache_key(query)
            r.setex(key, self._ttl, json.dumps(embedding))
        except Exception as e:
            logger.warning(f"Embedding cache set failed: {e}")


# Singleton instance
_cache: EmbeddingCache | None = None

def get_embedding_cache() -> EmbeddingCache:
    global _cache
    if _cache is None:
        from ..settings import settings
        _cache = EmbeddingCache(settings.redis_url, settings.embedding_cache_ttl)
    return _cache
