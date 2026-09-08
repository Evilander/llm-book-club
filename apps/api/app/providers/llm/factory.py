"""Factory for creating LLM clients."""
from __future__ import annotations

from ...settings import settings
from .base import LLMClient
from .openai import OpenAIClient
from .anthropic import AnthropicClient
from .gemini import GeminiClient
from .grok import GrokClient


def get_llm_client(provider: str | None = None) -> LLMClient:
    """
    Get an LLM client based on configuration.

    Args:
        provider: Override the configured provider

    Returns:
        LLMClient instance
    """
    provider = (provider or settings.llm_provider).lower()

    if provider == "openai":
        return OpenAIClient()
    elif provider == "claude" or provider == "anthropic":
        return AnthropicClient()
    elif provider == "gemini":
        return GeminiClient(model=settings.gemini_model)
    elif provider == "grok" or provider == "xai":
        return GrokClient(model=settings.grok_model)
    elif provider == "local":
        # Use OpenAI-compatible endpoint for local models
        if not settings.local_llm_base_url:
            raise ValueError("LOCAL_LLM_BASE_URL not configured")
        return OpenAIClient(
            api_key="local",
            base_url=settings.local_llm_base_url,
            model="default",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
