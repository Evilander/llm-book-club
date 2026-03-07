"""Google Gemini embeddings provider."""
from __future__ import annotations

import httpx

from ...settings import settings


class GeminiEmbeddings:
    """Google Gemini embeddings client using the Generative Language API."""

    MODEL_DIMENSIONS = {
        "text-embedding-004": 768,
        "embedding-001": 768,
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-004",
    ):
        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise ValueError("Gemini API key not configured (GEMINI_API_KEY)")
        self.model = model
        self._dimension = self.MODEL_DIMENSIONS.get(self.model, 768)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Gemini embedContent endpoint accepts a single text per request,
        so we process texts sequentially.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for text in texts:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta"
                    f"/models/{self.model}:embedContent"
                    f"?key={self.api_key}"
                )
                payload = {
                    "model": f"models/{self.model}",
                    "content": {
                        "parts": [{"text": text}],
                    },
                }

                response = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                embedding = data["embedding"]["values"]
                all_embeddings.append(embedding)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        embeddings = await self.embed([text])
        return embeddings[0] if embeddings else []
