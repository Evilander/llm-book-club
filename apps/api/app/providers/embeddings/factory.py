"""Factory for creating embeddings clients."""
from __future__ import annotations
from functools import lru_cache

from ...settings import settings
from .base import EmbeddingsClient
from .openai import OpenAIEmbeddings
from .space import configured_space, EmbeddingSpace


@lru_cache(maxsize=2)
def _local_client(space: EmbeddingSpace, device: str, cache_dir: str, threads: int):
    from .local import LocalEmbeddings
    return LocalEmbeddings(space, device=device, cache_dir=cache_dir, threads=threads)


def get_embeddings_client() -> EmbeddingsClient:
    """
    Get an embeddings client based on configuration.

    Returns:
        EmbeddingsClient instance
    """
    provider = settings.embeddings_provider.strip().lower()
    space = configured_space()

    if provider == "openai":
        return OpenAIEmbeddings()
    elif provider == "gemini":
        from .gemini import GeminiEmbeddings

        return GeminiEmbeddings()
    elif provider == "local":
        # If a LOCAL_EMBEDDINGS_BASE_URL is set, use the OpenAI-compatible
        # endpoint (e.g. Ollama).  Otherwise use sentence-transformers.
        if settings.local_embeddings_base_url:
            return OpenAIEmbeddings(
                api_key="local",
                base_url=settings.local_embeddings_base_url,
                model=space.model,
                dimension=space.dimension,
                query_prompt=space.query_prompt,
                document_prompt=space.document_prompt,
            )
        return _local_client(space, settings.local_embeddings_device, settings.local_embeddings_cache_dir, settings.local_embeddings_threads)
    else:
        raise ValueError(f"Unknown embeddings provider: {provider}")
