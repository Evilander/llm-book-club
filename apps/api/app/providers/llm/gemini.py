"""Google Gemini LLM provider."""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from ...settings import settings
from .base import LLMMessage, LLMResponse


class GeminiClient:
    """Google Gemini client using the REST API (no SDK)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
    ):
        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise ValueError("Gemini API key not configured")

        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

        # Populated after a stream() call is fully consumed
        self._last_stream_usage: LLMResponse | None = None

    def _format_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[str | None, list[dict]]:
        """
        Format messages for the Gemini API.

        Gemini uses a different structure:
        - system instructions go into a top-level `system_instruction` field
        - conversation messages use `contents` with roles "user" and "model"

        Returns (system_instruction_text, contents).
        """
        system_instruction = None
        contents: list[dict] = []

        for m in messages:
            if m.role == "system":
                # Gemini supports a single system instruction; concatenate if
                # multiple system messages appear (unlikely but safe).
                if system_instruction is None:
                    system_instruction = m.content
                else:
                    system_instruction += "\n\n" + m.content
            else:
                # Map "assistant" -> "model" for Gemini
                role = "model" if m.role == "assistant" else "user"
                contents.append({
                    "role": role,
                    "parts": [{"text": m.content}],
                })

        return system_instruction, contents

    @staticmethod
    def _extract_usage(data: dict) -> tuple[int, int]:
        """Extract input/output token counts from a Gemini response."""
        usage = data.get("usageMetadata", {})
        return (
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0),
        )

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a completion."""
        system_instruction, contents = self._format_messages(messages)

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}],
            }

        url = f"{self.base_url}/models/{self.model}:generateContent"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def complete_with_usage(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion and return content together with token usage."""
        system_instruction, contents = self._format_messages(messages)

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}],
            }

        url = f"{self.base_url}/models/{self.model}:generateContent"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            input_tokens, output_tokens = self._extract_usage(data)
            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=data.get("modelVersion", self.model),
            )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream a completion.

        After the stream is fully consumed, ``last_stream_usage`` will be
        populated with token counts from the final SSE chunk that Gemini
        emits with ``usageMetadata``.
        """
        self._last_stream_usage = None
        stream_input_tokens = 0
        stream_output_tokens = 0

        system_instruction, contents = self._format_messages(messages)

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}],
            }

        url = f"{self.base_url}/models/{self.model}:streamGenerateContent"

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                params={"key": self.api_key, "alt": "sse"},
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        try:
                            chunk = json.loads(data)
                            # Capture usage from any chunk (last one has
                            # cumulative totals)
                            if "usageMetadata" in chunk:
                                inp, out = self._extract_usage(chunk)
                                stream_input_tokens = inp
                                stream_output_tokens = out
                            candidates = chunk.get("candidates", [])
                            if candidates:
                                parts = (
                                    candidates[0]
                                    .get("content", {})
                                    .get("parts", [])
                                )
                                for part in parts:
                                    text = part.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue

        self._last_stream_usage = LLMResponse(
            content="",
            input_tokens=stream_input_tokens,
            output_tokens=stream_output_tokens,
            model=self.model,
        )

    @property
    def last_stream_usage(self) -> LLMResponse | None:
        """Token usage from the most recent ``stream()`` call."""
        return self._last_stream_usage
