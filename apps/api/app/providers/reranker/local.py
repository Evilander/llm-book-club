"""Local reranker provider using sentence-transformers CrossEncoder."""
from __future__ import annotations

import logging
from typing import Any

from .base import RerankResult

logger = logging.getLogger(__name__)


class LocalReranker:
    """
    Local reranker client using sentence-transformers CrossEncoder.

    The model is lazy-loaded on first call to avoid slow import/download
    at startup.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.device = device
        self._model: Any = None

    def _load_model(self) -> None:
        """Lazy-load the CrossEncoder model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for the local reranker. "
                "Install with: pip install sentence-transformers>=3.0.0"
            )

        logger.info(
            "Loading local reranker model %s on %s",
            self.model_name,
            self.device,
        )
        self._model = CrossEncoder(self.model_name, device=self.device)
        logger.info("Loaded reranker %s", self.model_name)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """
        Rerank documents using a local CrossEncoder model.

        Returns top_k results sorted by descending relevance score.
        """
        if not documents:
            return []

        self._load_model()
        assert self._model is not None

        top_k = min(top_k, len(documents))

        # CrossEncoder.predict expects list of (query, document) pairs
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(pairs, show_progress_bar=False)

        # Build scored results
        scored: list[RerankResult] = []
        for idx, (score, doc) in enumerate(zip(scores, documents)):
            scored.append(
                RerankResult(
                    index=idx,
                    score=float(score),
                    text=doc,
                )
            )

        # Sort by score descending and take top_k
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
