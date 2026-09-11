"""Shared query encoding for passage retrieval and conversation recall."""
import asyncio

from ..providers.embeddings.factory import get_embeddings_client
from ..providers.embeddings.space import EmbeddingSpace, storage_vector
from .cache import get_embedding_cache


async def query_vector(query: str, space: EmbeddingSpace, *, client=None, cache=None) -> list[float]:
    cache = cache if cache is not None else get_embedding_cache()
    vector = await asyncio.to_thread(cache.get, query, space.id)
    if vector is not None:
        try:
            return storage_vector(vector, space.dimension)
        except (TypeError, ValueError):
            pass  # A corrupt/stale cache entry cannot enter the vector query.
    client = client if client is not None else get_embeddings_client()
    vector = await client.embed_single(query)
    padded = storage_vector(vector, space.dimension)
    await asyncio.to_thread(cache.set, query, vector, space.id)
    return padded
