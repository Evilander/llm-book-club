"""Cohere reranker provider."""
from __future__ import annotations

import httpx

from ...settings import settings
from .base import RerankResult


class CohereReranker:
    """Cohere reranker client using the v2 Rerank API via httpx."""

    RERANK_URL = "https://api.cohere.com/v2/rerank"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "rerank-v3.5",
    ):
        self.api_key = api_key or settings.cohere_api_key
        if not self.api_key:
            raise ValueError("Cohere API key not configured (COHERE_API_KEY)")
        self.model = model

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """
        Rerank documents using Cohere Rerank v2 API.

        Returns top_k results sorted by descending relevance score.
        """
        if not documents:
            return []

        top_k = min(top_k, len(documents))

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.RERANK_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k,
                },
            )
            response.raise_for_status()
            data = response.json()

        results: list[RerankResult] = []
        for item in data["results"]:
            idx = item["index"]
            results.append(
                RerankResult(
                    index=idx,
                    score=item["relevance_score"],
                    text=documents[idx],
                )
            )

        # Already sorted by score descending from the API, but ensure it
        results.sort(key=lambda r: r.score, reverse=True)
        return results
