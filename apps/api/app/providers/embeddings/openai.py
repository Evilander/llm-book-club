"""OpenAI embeddings provider."""
from __future__ import annotations
import asyncio
import httpx
from typing import Any

from ...settings import settings


class OpenAIEmbeddings:
    """OpenAI embeddings client."""

    # Dimensions for each model
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.openai.com/v1",
    ):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url.rstrip("/")
        self.is_local = "localhost" in self.base_url or "ollama" in self.base_url or api_key == "local"

        # Only require API key for non-local providers
        if not self.api_key and not self.is_local:
            raise ValueError("OpenAI API key not configured")

        self.model = model or settings.openai_embeddings_model
        # For Ollama, use nomic-embed-text if not specified
        if self.is_local and self.model.startswith("text-embedding"):
            self.model = "nomic-embed-text"
        self._dimension = self.MODEL_DIMENSIONS.get(self.model, 768 if self.is_local else 3072)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts using OpenAI API."""
        if not texts:
            return []

        # OpenAI has a limit of ~8000 tokens per request
        # Process in batches if needed
        batch_size = 100
        all_embeddings = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                headers = {"Content-Type": "application/json"}
                if not self.is_local and self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                for attempt in range(5):
                    response = await client.post(
                        f"{self.base_url}/embeddings",
                        headers=headers,
                        json={
                            "input": batch,
                            "model": self.model,
                        },
                    )
                    if response.status_code == 429:
                        wait = min(2 ** attempt * 5, 60)
                        print(f"Rate limited, waiting {wait}s (attempt {attempt + 1}/5)")
                        await asyncio.sleep(wait)
                        continue
                    response.raise_for_status()
                    break
                else:
                    response.raise_for_status()
                data = response.json()

                # Sort by index to maintain order
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                batch_embeddings = [item["embedding"] for item in sorted_data]
                all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        embeddings = await self.embed([text])
        return embeddings[0] if embeddings else []
