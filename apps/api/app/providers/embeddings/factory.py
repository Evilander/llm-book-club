"""Factory for creating embeddings clients."""
from __future__ import annotations

from ...settings import settings
from .base import EmbeddingsClient
from .openai import OpenAIEmbeddings


def get_embeddings_client() -> EmbeddingsClient:
    """
    Get an embeddings client based on configuration.

    Returns:
        EmbeddingsClient instance
    """
    provider = settings.embeddings_provider.lower()

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
            )

        from .local import LocalEmbeddings

        return LocalEmbeddings(model_name=settings.local_embeddings_model)
    else:
        raise ValueError(f"Unknown embeddings provider: {provider}")
