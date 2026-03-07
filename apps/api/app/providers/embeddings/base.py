from __future__ import annotations
from typing import Protocol


class EmbeddingsClient(Protocol):
    """Protocol for embeddings providers."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed

        Returns:
            List of embedding vectors (same length as input)
        """
        ...

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...
