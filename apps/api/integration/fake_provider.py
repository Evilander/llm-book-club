"""Deterministic HTTP provider for integration tests, never used by the product."""
import asyncio
import json
import re

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    payload = await request.json()
    inputs = payload["input"]
    if isinstance(inputs, str):
        inputs = [inputs]
    return {"data": [{"index": i, "embedding": [1.0] + [0.0] * 3071} for i, _ in enumerate(inputs)]}


@app.post("/v1/chat/completions")
async def complete(request: Request):
    payload = await request.json()
    messages = payload["messages"]
    system = messages[0]["content"]
    if "CURRENT PAGE" in system:
        current = json.loads(messages[-1]["content"])["current_page"]
        match = re.search(r"[^.!?\n]+[.!?]", current)
        quote = match.group(0).strip() if match else current.strip()[:120]
        answer = json.dumps({"notes": [{"quote": quote, "question": "What does the compass ask the reader to trust?"}]})
    else:
        evidence = re.search(r'\[([a-f0-9-]{36})\]:\n"([^"]+)"', system)
        if evidence:
            chunk_id, passage = evidence.groups()
            quote = passage.strip().split(".")[0] + "."
            memory = any("cobalt-thread" in m["content"] for m in messages[1:-1])
            prefix = "I remember your cobalt-thread observation. " if memory else ""
            answer = prefix + f'The compass invites a question about trust. [cite: {chunk_id}, "{quote}"] What do you notice?'
        else:
            answer = "What would you like to look at together?"
    if not payload.get("stream"):
        return {"choices": [{"message": {"content": answer}}], "usage": {"prompt_tokens": 20, "completion_tokens": 20}, "model": "integration-fixture"}
    async def events():
        for start in range(0, len(answer), 13):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": answer[start:start+13]}}]}) + "\n\n"
            await asyncio.sleep(0.005)
        yield 'data: {"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":20}}\n\n'
        yield "data: [DONE]\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
