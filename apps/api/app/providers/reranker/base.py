"""Base protocol for reranker providers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RerankResult:
    """A single reranked document with its score."""

    index: int
    score: float
    text: str


class RerankerClient(Protocol):
    """Protocol for reranker providers."""

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """
        Rerank documents by relevance to a query.

        Args:
            query: The search query.
            documents: List of document texts to rerank.
            top_k: Number of top results to return.

        Returns:
            List of RerankResult sorted by descending relevance score.
        """
        ...
