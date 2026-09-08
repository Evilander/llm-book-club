"""OpenAI TTS provider."""
from __future__ import annotations
from typing import AsyncIterator

import httpx

from ...settings import settings
from .base import TTSRequest


class OpenAITTS:
    """OpenAI text-to-speech client."""

    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        default_voice: str = "alloy",
    ):
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        self.model = model or settings.tts_model or "tts-1"
        self.base_url = base_url.rstrip("/")
        self.default_voice = default_voice

    async def synthesize(self, req: TTSRequest) -> bytes:
        """Synthesize speech from text."""
        voice = req.voice or self.default_voice
        model = req.model or self.model

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
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
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
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
