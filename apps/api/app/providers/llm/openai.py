"""OpenAI LLM provider."""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from ...settings import settings
from .base import LLMMessage, LLMResponse


class OpenAIClient:
    """OpenAI chat completion client (also supports Ollama and other compatible APIs)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
    ):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url.rstrip("/")
        self.is_local = "localhost" in self.base_url or "ollama" in self.base_url or api_key == "local"

        # Only require API key for non-local providers
        if not self.api_key and not self.is_local:
            raise ValueError("OpenAI API key not configured")

        self.model = model
        # For Ollama, use llama3.2 if model is "default" or starts with "gpt"
        if self.is_local and (model == "default" or model.startswith("gpt")):
            self.model = "llama3.2"

        # Populated after a stream() call is fully consumed
        self._last_stream_usage: LLMResponse | None = None

    def _format_messages(self, messages: list[LLMMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _get_headers(self) -> dict:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if not self.is_local and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a completion."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": self.model,
                    "messages": self._format_messages(messages),
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def complete_with_usage(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion and return content together with token usage."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": self.model,
                    "messages": self._format_messages(messages),
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return LLMResponse(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                model=data.get("model", self.model),
            )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream a completion.

        After the stream is fully consumed, ``last_stream_usage`` will be
        populated with token counts if the API returned a final usage chunk
        (requires ``stream_options: {"include_usage": true}``).
        """
        self._last_stream_usage = None
        stream_input_tokens = 0
        stream_output_tokens = 0
        stream_model = self.model

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": self.model,
                    "messages": self._format_messages(messages),
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            # Capture model name from any chunk
                            if "model" in chunk:
                                stream_model = chunk["model"]
                            # The final chunk with usage has choices=[] and
                            # a top-level "usage" key.
                            if "usage" in chunk and chunk["usage"]:
                                usage = chunk["usage"]
                                stream_input_tokens = usage.get("prompt_tokens", 0)
                                stream_output_tokens = usage.get("completion_tokens", 0)
                            delta = chunk["choices"][0].get("delta", {}) if chunk.get("choices") else {}
                            if "content" in delta:
                                yield delta["content"]
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue

        self._last_stream_usage = LLMResponse(
            content="",
            input_tokens=stream_input_tokens,
            output_tokens=stream_output_tokens,
            model=stream_model,
        )

    @property
    def last_stream_usage(self) -> LLMResponse | None:
        """Token usage from the most recent ``stream()`` call."""
        return self._last_stream_usage
