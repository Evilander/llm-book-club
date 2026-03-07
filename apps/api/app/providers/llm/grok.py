"""xAI Grok LLM provider (OpenAI-compatible API)."""
from __future__ import annotations

from ...settings import settings
from .openai import OpenAIClient


class GrokClient(OpenAIClient):
    """
    xAI Grok client.

    Grok exposes an OpenAI-compatible API at https://api.x.ai/v1,
    so this class simply extends OpenAIClient with the correct
    base URL, API key, and default model.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "grok-3",
    ):
        resolved_key = api_key or settings.grok_api_key
        if not resolved_key:
            raise ValueError("Grok API key not configured")

        super().__init__(
            api_key=resolved_key,
            model=model,
            base_url="https://api.x.ai/v1",
        )
