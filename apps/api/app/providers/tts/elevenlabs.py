"""ElevenLabs TTS provider."""
from __future__ import annotations
from typing import AsyncIterator

import httpx

from ...settings import settings
from .base import TTSRequest


class ElevenLabsTTS:
    """ElevenLabs text-to-speech client."""

    # Map OpenAI voice names to ElevenLabs voice IDs
    VOICE_MAP = {
        "alloy": "21m00Tcm4TlvDq8ikWAM",  # Rachel - similar professional tone
        "echo": "D38z5RcWu1voky8WS1ja",   # Fin - male voice
        "fable": "EXAVITQu4vr4xnSDxMaL",  # Sarah - storytelling
        "onyx": "TX3LPaxmHKxFdv7VOQHJ",   # Liam - deep male
        "nova": "EXAVITQu4vr4xnSDxMaL",   # Sarah - friendly female
        "shimmer": "21m00Tcm4TlvDq8ikWAM", # Rachel - soft female
    }

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = "eleven_turbo_v2_5",
    ):
        self.api_key = api_key or settings.elevenlabs_api_key
        if not self.api_key:
            raise ValueError("ElevenLabs API key not configured")

        self.voice_id = voice_id or settings.elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel
        self.model_id = model_id
        self.base_url = "https://api.elevenlabs.io/v1"

    def _resolve_voice(self, voice: str | None) -> str:
        """Resolve voice name/ID to ElevenLabs voice ID."""
        if not voice:
            return self.voice_id
        # If it's an OpenAI voice name, map it
        if voice.lower() in self.VOICE_MAP:
            return self.VOICE_MAP[voice.lower()]
        # If it looks like an ElevenLabs ID (long alphanumeric), use it directly
        if len(voice) > 15:
            return voice
        # Default to configured voice
        return self.voice_id

    async def synthesize(self, req: TTSRequest) -> bytes:
        """Synthesize speech from text."""
        voice_id = self._resolve_voice(req.voice)
        model = req.model or self.model_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": req.text,
                    "model_id": model,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )
            response.raise_for_status()
            return response.content

    async def stream(self, req: TTSRequest) -> AsyncIterator[bytes]:
        """Stream synthesized speech."""
        voice_id = self._resolve_voice(req.voice)
        model = req.model or self.model_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/text-to-speech/{voice_id}/stream",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": req.text,
                    "model_id": model,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk
