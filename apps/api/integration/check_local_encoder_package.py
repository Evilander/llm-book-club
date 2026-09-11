"""Run inside the CPU-enabled API image with its model cache mounted.

Run with network disabled after downloading the pinned model. This verifies
the actual packaged dependencies, permissions, and query/document behavior.
"""
import asyncio
import json
import math
import os
import time
from pathlib import Path

from app.providers.embeddings.factory import get_embeddings_client
from app.providers.embeddings.space import configured_space, storage_vector


async def check():
    import torch
    assert os.getuid() == 1001
    assert not torch.cuda.is_available()
    space = configured_space()
    assert space.provider == "local"
    client = get_embeddings_client()
    assert get_embeddings_client() is client
    started = time.perf_counter()
    documents = await client.embed(["I saw his silence as grief, not indifference.", "The red bicycle needed a new wheel."])
    query = await client.embed_single("Did I think he stopped speaking because he was mourning?")
    assert len(query) == space.dimension == 1024
    assert all(math.isfinite(value) for vector in documents + [query] for value in vector)
    scores = [sum(x*y for x,y in zip(query, doc)) for doc in documents]
    assert scores[0] > scores[1]
    assert len(storage_vector(query, space.dimension)) == 3072
    cache = Path(os.environ["LOCAL_EMBEDDINGS_CACHE_DIR"])
    probe = cache / "write-probe.txt"
    probe.write_text("fixture")
    probe.unlink()
    print(json.dumps({"status": "passed", "torch": torch.__version__, "native_dimension": len(query), "elapsed_seconds": time.perf_counter() - started, "offline": os.environ.get("HF_HUB_OFFLINE") == "1"}))


asyncio.run(check())
