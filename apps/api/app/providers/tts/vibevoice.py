"""VibeVoice TTS provider (OpenAI-compatible proxy)."""
from __future__ import annotations
from typing import AsyncIterator

import httpx

from ...settings import settings
from .base import TTSRequest


class VibeVoiceTTS:
    """
    VibeVoice text-to-speech client.

    VibeVoice exposes an OpenAI-compatible TTS API, so this is
    essentially a wrapper around the OpenAI TTS client with a
    different base URL.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        default_voice: str = "alloy",
    ):
        self.base_url = (base_url or settings.tts_base_url or "http://localhost:8001/v1").rstrip("/")
        self.model = model or settings.tts_model or "tts-1"
        self.default_voice = default_voice

    async def synthesize(self, req: TTSRequest) -> bytes:
        """Synthesize speech from text."""
        voice = req.voice or self.default_voice
        model = req.model or self.model

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "input": req.text,
                    "voice": voice,
                    "speed": req.speed,
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            return response.content

    async def stream(self, req: TTSRequest) -> AsyncIterator[bytes]:
        """Stream synthesized speech."""
        voice = req.voice or self.default_voice
        model = req.model or self.model

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/audio/speech",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "input": req.text,
                    "voice": voice,
                    "speed": req.speed,
                    "response_format": "mp3",
                },
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk
