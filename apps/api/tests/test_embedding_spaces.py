import asyncio
from dataclasses import replace
import json
import math
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.providers.embeddings.space import EmbeddingSpace, configured_space, storage_batch, storage_vector
from app.providers.embeddings.local import LocalEmbeddings
from app.retrieval.cache import EmbeddingCache
from app.retrieval.embedding import query_vector
from app.settings import settings


def test_padding_preserves_cosine_and_all_native_coordinates():
    a, b = [3.0, -2.0, 4.0], [-1.0, 5.0, 7.0]
    expected = sum(x*y for x,y in zip(a,b)) / (math.hypot(*a)*math.hypot(*b))
    padded_a, padded_b = storage_vector(a, 3), storage_vector(b, 3)
    assert len(padded_a) == 3072 and padded_a[3:] == [0.0] * 3069
    assert sum(x*y for x,y in zip(padded_a,padded_b)) == pytest.approx(expected)


@pytest.mark.parametrize("vector", [[0.0]*3, [True, 0, 1], [float('nan'), 1, 2], [float('inf'), 1, 2], [1.0, 2.0], ["1", 2, 3]])
def test_invalid_vectors_never_enter_storage(vector):
    with pytest.raises(ValueError):
        storage_vector(vector, 3)


def test_batch_count_mismatch_is_not_silently_zipped_away():
    with pytest.raises(ValueError, match="incomplete batch"):
        storage_batch([[1.0, 0.0]], 2, 2)


def test_model_contract_changes_invalidate_vectors_but_keys_do_not(monkeypatch):
    first = EmbeddingSpace("local", "fixture", 3, "a"*40)
    for changed in [replace(first, model="other"), replace(first, dimension=4), replace(first, revision="b"*40), replace(first, query_prompt="query: "), replace(first, document_prompt="passage: "), replace(first, max_tokens=1024), replace(first, endpoint_hash="other")]:
        assert changed.id != first.id
    before = configured_space().id
    monkeypatch.setattr(settings, "openai_api_key", "fixture-rotated-credential")
    assert configured_space().id == before


def test_unknown_local_model_requires_pinned_revision(monkeypatch):
    monkeypatch.setattr(settings, "embeddings_provider", "local")
    monkeypatch.setattr(settings, "local_embeddings_base_url", None)
    monkeypatch.setattr(settings, "local_embeddings_model", "example/unpinned-model")
    monkeypatch.setattr(settings, "local_embeddings_revision", None)
    with pytest.raises(ValueError, match="full commit hash"):
        configured_space()


def test_endpoint_uses_configured_model_and_dimension(monkeypatch):
    from app.providers.embeddings.factory import get_embeddings_client
    monkeypatch.setattr(settings, "embeddings_provider", "local")
    monkeypatch.setattr(settings, "local_embeddings_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "local_embeddings_model", "fixture-embedding")
    monkeypatch.setattr(settings, "local_embeddings_revision", "fixture-v1")
    monkeypatch.setattr(settings, "local_embeddings_dimension", 768)
    client = get_embeddings_client()
    assert client.model == "fixture-embedding" and client.dimension == 768


def test_http_encoder_requires_explicit_deployment_revision(monkeypatch):
    monkeypatch.setattr(settings, "embeddings_provider", "local")
    monkeypatch.setattr(settings, "local_embeddings_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "local_embeddings_revision", None)
    with pytest.raises(ValueError, match="deployment version"):
        configured_space()


@pytest.mark.asyncio
async def test_model_scoped_cache_recomputes_corrupt_dimension():
    space = EmbeddingSpace("test", "fixture", 3)
    client = MagicMock(embed_single=AsyncMock(return_value=[1., 2., 3.]))
    cache = MagicMock()
    cache.get.return_value = [1., 2.]
    result = await query_vector("a private thought", space, client=client, cache=cache)
    assert len(result) == 3072
    client.embed_single.assert_awaited_once()
    cache.set.assert_called_once_with("a private thought", [1., 2., 3.], space.id)


def test_cache_never_logs_queries_or_connection_errors(caplog):
    cache = EmbeddingCache("redis://localhost:1")
    cache._redis = MagicMock()
    cache._redis.get.side_effect = RuntimeError("PRIVATE_CREDENTIAL")
    with caplog.at_level("DEBUG"):
        assert cache.get("PRIVATE_THOUGHT", "space") is None
    assert "PRIVATE" not in caplog.text
    assert cache._cache_key("same", "first") != cache._cache_key("same", "second")


@pytest.mark.parametrize("value", [[float('nan')], [True], [], [0.0], {"vector": [1.0]}])
def test_corrupt_cache_values_are_misses(value):
    cache = EmbeddingCache("redis://localhost:1")
    cache._redis = MagicMock()
    cache._redis.get.return_value = json.dumps(value)
    assert cache.get("query", "space") is None


@pytest.mark.asyncio
async def test_local_inference_keeps_event_loop_responsive_and_uses_task_prompts():
    client = LocalEmbeddings(EmbeddingSpace("local", "fixture", 3, query_prompt="query: ", document_prompt="passage: "), device="cpu", cache_dir="unused", threads=1)
    prompts = []
    main_thread = threading.get_ident()
    class Model:
        def encode(self, texts, **kwargs):
            assert threading.get_ident() != main_thread
            prompts.append(kwargs["prompt"])
            time.sleep(0.06)
            return MagicMock(tolist=lambda: [[1., 0., 0.] for _ in texts])
    client._model = Model()
    ticks = 0
    async def heartbeat():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.005)
            ticks += 1
    await asyncio.gather(client.embed(["a thought"]), client.embed_single("a query"), heartbeat())
    assert ticks == 5 and set(prompts) == {"passage: ", "query: "}
