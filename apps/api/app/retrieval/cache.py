"""One-hour query cache, isolated by the full embedding contract."""
import hashlib
import json
import logging
import math

logger = logging.getLogger(__name__)


class EmbeddingCache:
    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        self._redis = None
        self._redis_url = redis_url
        self._ttl = ttl_seconds

    def _get_redis(self):
        if self._redis is None:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url, socket_connect_timeout=0.25, socket_timeout=0.25,
            )
        return self._redis

    def _cache_key(self, query: str, space_id: str) -> str:
        digest = hashlib.sha256(json.dumps([space_id, "query", query], ensure_ascii=False).encode()).hexdigest()
        return f"embed_cache:v2:{digest}"

    def get(self, query: str, space_id: str) -> list[float] | None:
        try:
            data = self._get_redis().get(self._cache_key(query, space_id))
            vector = json.loads(data) if data else None
            if isinstance(vector, list) and vector and len(vector) <= 3072 and all(type(x) in (int, float) and math.isfinite(x) for x in vector) and any(vector):
                return vector
        except Exception as exc:
            # Queries, URLs, and exception messages can contain private data.
            logger.debug("Embedding cache unavailable (%s)", type(exc).__name__)
        return None

    def set(self, query: str, embedding: list[float], space_id: str) -> None:
        try:
            self._get_redis().setex(self._cache_key(query, space_id), self._ttl, json.dumps(embedding, allow_nan=False))
        except Exception as exc:
            logger.debug("Embedding cache write unavailable (%s)", type(exc).__name__)


_cache: EmbeddingCache | None = None


def get_embedding_cache() -> EmbeddingCache:
    global _cache
    if _cache is None:
        from ..settings import settings
        _cache = EmbeddingCache(settings.redis_url, settings.embedding_cache_ttl)
    return _cache
