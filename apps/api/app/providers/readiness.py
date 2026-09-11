"""Check connection prerequisites without generating text or spending API credits."""
import asyncio
import json

import httpx
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..settings import settings
from .llm.codex_runtime import CodexUnavailable, get_codex_runtime
from .selection import canonical_provider, selected_provider


class ReadingConnection(BaseModel):
    provider: str
    connected: bool
    message: str


async def chatgpt_status() -> dict:
    runtime = get_codex_runtime()
    if not runtime.available:
        return {"connected": False, "ready": False, "note": "Install the ChatGPT connection runtime, or use the Docker setup."}
    try:
        async with asyncio.timeout(6):
            account = await runtime.account()
        search_note = " Book search uses the OpenAI API separately." if settings.embeddings_provider.lower() == "openai" else " Book search and voice keep their separate provider settings."
        return {**account, "ready": True, "note": "Uses the Codex access included with your ChatGPT plan. Its usage limits apply." + search_note}
    except (CodexUnavailable, TimeoutError):
        return {"connected": False, "ready": False, "note": "The ChatGPT connection is unavailable. Check the reading service and try again."}


async def local_status() -> ReadingConnection:
    message = "Start your local model server and install the selected model, then check again."
    if not settings.local_llm_base_url:
        return ReadingConnection(provider="local", connected=False, message="Your local model needs server setup. You can choose another reading partner in Settings.")
    try:
        # Read the installed model list only. Never load a model or run inference
        # merely because someone opens Settings. Redirects are intentionally off.
        async with asyncio.timeout(3), httpx.AsyncClient(timeout=2, follow_redirects=False) as client:
            async with client.stream("GET", f"{settings.local_llm_base_url.rstrip('/')}/models") as response:
                response.raise_for_status()
                body = bytearray()
                async for part in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(body) + len(part) > 512_000:
                        raise ValueError("Model list too large")
                    body.extend(part)
        data = json.loads(body)
        models = {item.get("id") for item in data["data"] if isinstance(item, dict) and isinstance(item.get("id"), str)}
        model = settings.local_llm_model
        # Ollama lists an untagged model as :latest; explicit tags stay exact.
        connected = model in models or (":" not in model and f"{model}:latest" in models)
        if connected:
            message = "Your selected local model is available."
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
        connected = False
    return ReadingConnection(provider="local", connected=connected, message=message)


async def reading_connection(db: Session, provider: str | None = None) -> ReadingConnection:
    provider = canonical_provider(provider) if provider else selected_provider(db)
    if provider == "local":
        return await local_status()
    if provider == "chatgpt":
        status = await chatgpt_status()
        return ReadingConnection(provider=provider, connected=status["connected"], message="ChatGPT is connected." if status["connected"] else "Connect ChatGPT to continue reading together, or choose another reading partner.")
    if provider == "gemini" and settings.gemini_auth_mode.lower().strip() == "oauth":
        from ..auth.service import get_google_connection
        connected = bool(settings.google_oauth_project_id and get_google_connection(db))
    else:
        # Presence is a prerequisite, not a live validation of an API account.
        connected = bool({"openai": settings.openai_api_key, "anthropic": settings.anthropic_api_key, "gemini": settings.gemini_api_key, "grok": settings.grok_api_key}.get(provider))
    return ReadingConnection(provider=provider, connected=connected, message="A reading connection is configured." if connected else "Choose a reading partner to start a conversation. Your place and draft will stay here.")


async def require_reading_connection(db: Session) -> None:
    status = await reading_connection(db)
    if not status.connected:
        raise HTTPException(409, {"code": "reading_connection_required", **status.model_dump()}, headers={"Cache-Control": "no-store"})
