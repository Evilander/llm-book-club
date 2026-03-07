"""Factory for creating reranker clients."""
from __future__ import annotations

from ...settings import settings
from .base import RerankerClient


def get_reranker_client() -> RerankerClient | None:
    """
    Get a reranker client based on configuration.

    Returns None if RERANKER_PROVIDER is set to "none" (the default),
    meaning no reranking will be applied.

    Returns:
        RerankerClient instance, or None if reranking is disabled.
    """
    provider = settings.reranker_provider.lower()

    if provider == "none":
        return None
    elif provider == "cohere":
        from .cohere import CohereReranker

        return CohereReranker(model=settings.reranker_model)
    elif provider == "local":
        from .local import LocalReranker

        return LocalReranker(model_name=settings.local_reranker_model)
    else:
        raise ValueError(f"Unknown reranker provider: {provider}")
