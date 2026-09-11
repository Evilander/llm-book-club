"""A vector is meaningful only in the exact space that produced it."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from ...settings import settings

STORAGE_DIMENSION = 3072
LOCAL_MODEL = "Qwen/Qwen3-Embedding-0.6B"
LOCAL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QUERY_PROMPT = "Instruct: Given a reading question, retrieve relevant book passages and earlier reader thoughts.\nQuery: "


@dataclass(frozen=True)
class EmbeddingSpace:
    provider: str
    model: str
    dimension: int
    revision: str = "provider-managed"
    query_prompt: str = ""
    document_prompt: str = ""
    max_tokens: int | None = None
    endpoint_hash: str = ""
    contract: str = "normalized-zero-pad-v1"

    @property
    def id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def configured_space() -> EmbeddingSpace:
    provider = settings.embeddings_provider.strip().lower()
    if provider == "openai":
        dimensions = {"text-embedding-3-large": 3072, "text-embedding-3-small": 1536, "text-embedding-ada-002": 1536}
        model = settings.openai_embeddings_model
        if model not in dimensions:
            raise ValueError("Configure a supported OpenAI embedding model.")
        return EmbeddingSpace(provider, model, dimensions[model])
    if provider == "gemini":
        return EmbeddingSpace(provider, "text-embedding-004", 768)
    if provider != "local":
        raise ValueError("Unknown embedding provider.")
    model = settings.local_embeddings_model
    endpoint = settings.local_embeddings_base_url
    if endpoint:
        url = urlsplit(endpoint)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use an HTTP embedding base URL without credentials, query parameters, or fragments.")
    revision = settings.local_embeddings_revision
    if endpoint and not (revision and revision.strip()):
        raise ValueError("Set LOCAL_EMBEDDINGS_REVISION to the server's model digest or deployment version.")
    if not endpoint:
        revision = revision or (LOCAL_REVISION if model == LOCAL_MODEL else None)
        if not revision or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Pin LOCAL_EMBEDDINGS_REVISION to the model's full commit hash.")
    return EmbeddingSpace(
        "local-api" if endpoint else "local", model, settings.local_embeddings_dimension,
        revision,
        settings.local_embeddings_query_prompt if settings.local_embeddings_query_prompt is not None else (QUERY_PROMPT if model == LOCAL_MODEL else ""),
        settings.local_embeddings_document_prompt,
        settings.local_embeddings_max_tokens if not endpoint else None,
        hashlib.sha256(endpoint.rstrip("/").encode()).hexdigest() if endpoint else "",
    )


def storage_vector(vector: list[float], dimension: int) -> list[float]:
    """Normalize and zero-pad without changing cosine; always match space IDs."""
    if not 1 <= dimension <= STORAGE_DIMENSION or len(vector) != dimension:
        raise ValueError("The embedding provider returned an unexpected vector dimension.")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
        raise ValueError("The embedding provider returned a non-finite vector.")
    norm = math.hypot(*vector)
    if not norm or not math.isfinite(norm):
        raise ValueError("The embedding provider returned an empty or invalid vector.")
    return [float(x / norm) for x in vector] + [0.0] * (STORAGE_DIMENSION - dimension)


def storage_batch(vectors: list[list[float]], count: int, dimension: int) -> list[list[float]]:
    if not count:
        raise ValueError("No readable passages were found in this file.")
    if len(vectors) != count:
        raise ValueError("The embedding provider returned an incomplete batch.")
    return [storage_vector(vector, dimension) for vector in vectors]
