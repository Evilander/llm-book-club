"""Factory for creating TTS clients."""
from __future__ import annotations

from ...settings import settings
from .base import TTSClient
from .openai import OpenAITTS
from .elevenlabs import ElevenLabsTTS
from .vibevoice import VibeVoiceTTS


def get_tts_client(provider: str | None = None) -> TTSClient:
    """
    Get a TTS client based on configuration.

    Args:
        provider: Override the configured provider

    Returns:
        TTSClient instance
    """
    provider = (provider or settings.tts_provider).lower()

    if provider == "openai":
        return OpenAITTS()
    elif provider == "elevenlabs":
        return ElevenLabsTTS()
    elif provider == "vibevoice":
        return VibeVoiceTTS()
    else:
        raise ValueError(f"Unknown TTS provider: {provider}")
