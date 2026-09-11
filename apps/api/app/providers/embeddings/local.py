"""Pinned local encoder, loaded once per process and run off the event loop."""
import asyncio
from pathlib import Path
import threading
from typing import Any

from .space import EmbeddingSpace


class LocalEmbeddings:
    def __init__(self, space: EmbeddingSpace, *, device: str, cache_dir: str, threads: int):
        self.space = space
        self.device = device
        self.cache_dir = cache_dir
        self.threads = threads
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def dimension(self) -> int:
        return self.space.dimension

    def _encode(self, texts: list[str], *, query: bool) -> list[list[float]]:
        # One load/inference at a time, including after a cancelled coroutine.
        with self._lock:
            if self._model is None:
                try:
                    import torch
                    from sentence_transformers import SentenceTransformer
                except ImportError:
                    raise RuntimeError("Install requirements-local.txt to use local book search.") from None
                Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
                torch.set_num_threads(self.threads)
                model = SentenceTransformer(
                    self.space.model, revision=self.space.revision,
                    device=self.device, cache_folder=self.cache_dir,
                    trust_remote_code=False, token=False,
                    model_kwargs={"use_safetensors": True},
                )
                if model.get_sentence_embedding_dimension() != self.space.dimension:
                    raise ValueError("LOCAL_EMBEDDINGS_DIMENSION does not match the pinned model.")
                model.max_seq_length = self.space.max_tokens
                self._model = model
            vectors = self._model.encode(
                texts, batch_size=8, show_progress_bar=False,
                normalize_embeddings=True,
                prompt=self.space.query_prompt if query else self.space.document_prompt,
            )
            return vectors.tolist()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, texts, query=False) if texts else []

    async def embed_single(self, text: str) -> list[float]:
        return (await asyncio.to_thread(self._encode, [text], query=True))[0]
