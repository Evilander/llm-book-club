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

        # Explicit local IDs (including gpt-oss and aliases) stay unchanged.
        self.model = model

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

    def _request_body(self, messages: list[LLMMessage], temperature: float, max_tokens: int) -> dict:
        body = {"model": self.model, "messages": self._format_messages(messages),
                "temperature": temperature, "max_tokens": max_tokens}
        if self.is_local and settings.local_llm_reasoning_effort != "provider":
            body["reasoning_effort"] = settings.local_llm_reasoning_effort
        return body

    @staticmethod
    def _check_answer(content: str, finish_reason: str | None) -> None:
        if finish_reason == "length":
            raise ValueError("The model reached its response limit before finishing. Try a shorter reply or lower local reasoning effort.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned no answer. Try again or check the model settings.")

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a complete, non-empty answer."""
        return (await self.complete_with_usage(messages, temperature, max_tokens)).content

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
                json=self._request_body(messages, temperature, max_tokens),
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content")
            self._check_answer(content, choice.get("finish_reason"))
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
        finish_reason = None
        saw_done = False
        has_content = False

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json={
                    **self._request_body(messages, temperature, max_tokens),
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            saw_done = True
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
                            choice = chunk["choices"][0] if chunk.get("choices") else {}
                            finish_reason = choice.get("finish_reason") or finish_reason
                            delta = choice.get("delta", {})
                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                has_content = has_content or bool(content.strip())
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue

        self._last_stream_usage = LLMResponse(
            content="",
            input_tokens=stream_input_tokens,
            output_tokens=stream_output_tokens,
            model=stream_model,
        )
        if not saw_done and finish_reason is None:
            raise ValueError("The model stream ended before the answer was complete.")
        self._check_answer("answer" if has_content else "", finish_reason)

    @property
    def last_stream_usage(self) -> LLMResponse | None:
        """Token usage from the most recent ``stream()`` call."""
        return self._last_stream_usage
