from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, AsyncIterator


@dataclass
class TTSRequest:
    """Request for text-to-speech synthesis."""
    text: str
    voice: str | None = None
    model: str | None = None
    speed: float = 1.0


class TTSClient(Protocol):
    """Protocol for TTS providers."""

    async def synthesize(self, req: TTSRequest) -> bytes:
        """
        Synthesize speech from text.

        Args:
            req: TTS request with text and options

        Returns:
            Audio data as bytes (MP3 format)
        """
        ...

    async def stream(self, req: TTSRequest) -> AsyncIterator[bytes]:
        """
        Stream synthesized speech.

        Args:
            req: TTS request with text and options

        Yields:
            Audio chunks as they become available
        """
        ...
