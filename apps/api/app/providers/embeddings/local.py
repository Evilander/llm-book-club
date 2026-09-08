"""Local embeddings provider using sentence-transformers."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LocalEmbeddings:
    """
    Local embeddings client using sentence-transformers.

    The model is lazy-loaded on first call to avoid slow import/download
    at startup.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.device = device
        self._model: Any = None
        self._dimension: int | None = None

    def _load_model(self) -> None:
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install with: pip install sentence-transformers>=3.0.0"
            )

        logger.info(
            "Loading local embeddings model %s on %s",
            self.model_name,
            self.device,
        )
        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(
            "Loaded %s — dimension=%d", self.model_name, self._dimension
        )

    @property
    def dimension(self) -> int:
        self._load_model()
        assert self._dimension is not None
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        sentence-transformers encode() is synchronous and handles batching
        internally, so we call it directly.  For truly non-blocking behaviour
        in a production async server you would want to run this in a thread
        pool; for simplicity we call it inline here.
        """
        if not texts:
            return []

        self._load_model()
        assert self._model is not None

        # encode returns a numpy ndarray of shape (len(texts), dim)
        embeddings = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        return [vec.tolist() for vec in embeddings]

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        embeddings = await self.embed([text])
        return embeddings[0] if embeddings else []
