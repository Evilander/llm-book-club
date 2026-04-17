"""Anthropic Claude LLM provider."""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from ...settings import settings
from .base import EVIDENCE_CACHE_BOUNDARY, LLMMessage, LLMResponse


# Minimum byte length Anthropic requires for a cache block to be billable.
# Below this the API accepts cache_control but never produces a cache hit,
# so we skip marking the prefix as cacheable (saves a tiny amount of
# payload on non-agent calls like the classifier).
_MIN_CACHEABLE_CHARS = 1024


class AnthropicClient:
    """Anthropic Claude client."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
    ):
        self.api_key = api_key or settings.anthropic_api_key
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")

        self.model = model
        self.base_url = "https://api.anthropic.com/v1"

        # Populated after a stream() call is fully consumed
        self._last_stream_usage: LLMResponse | None = None

    def _build_system_blocks(self, system_prompt: str) -> list[dict]:
        """
        Convert a system prompt string into Anthropic content blocks with
        cache_control attached to the stable prefix when worth caching.

        The agent layer inserts ``EVIDENCE_CACHE_BOUNDARY`` between the
        stable personality/role prefix and per-turn retrieval evidence.
        We split on it and tag the stable prefix for prompt caching.
        """
        if EVIDENCE_CACHE_BOUNDARY in system_prompt:
            stable, _, evidence = system_prompt.partition(EVIDENCE_CACHE_BOUNDARY)
            blocks: list[dict] = []
            if stable.strip():
                stable_block: dict = {"type": "text", "text": stable}
                if len(stable) >= _MIN_CACHEABLE_CHARS:
                    stable_block["cache_control"] = {"type": "ephemeral"}
                blocks.append(stable_block)
            if evidence.strip():
                blocks.append({"type": "text", "text": evidence})
            return blocks

        # No boundary marker: cache the whole system prompt if it's large
        # enough to be worth it.
        block: dict = {"type": "text", "text": system_prompt}
        if len(system_prompt) >= _MIN_CACHEABLE_CHARS:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]

    def _format_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[list[dict] | None, list[dict]]:
        """
        Format messages for Anthropic API.
        Returns (system_blocks, messages). ``system_blocks`` is either
        ``None`` (no system message) or a list of content blocks with
        cache_control markers as appropriate.
        """
        system_prompt: str | None = None
        formatted: list[dict] = []

        for m in messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                formatted.append({"role": m.role, "content": m.content})

        system_blocks = (
            self._build_system_blocks(system_prompt)
            if system_prompt
            else None
        )
        return system_blocks, formatted

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a completion."""
        system_blocks, formatted_messages = self._format_messages(messages)

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_blocks:
            payload["system"] = system_blocks

        assert self.api_key is not None  # checked in __init__
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers=self._headers(self.api_key),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]

    async def complete_with_usage(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a completion and return content together with token usage."""
        system_blocks, formatted_messages = self._format_messages(messages)

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_blocks:
            payload["system"] = system_blocks

        assert self.api_key is not None
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers=self._headers(self.api_key),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            # Prompt-caching usage fields (cache_creation_input_tokens,
            # cache_read_input_tokens) are additive to input_tokens in
            # Anthropic's accounting. We surface only the primary counts
            # here; observability dashboards can query the raw response
            # separately if finer cache-hit breakdown is needed.
            return LLMResponse(
                content=content,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
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
        populated with token counts from the ``message_delta`` event that
        Anthropic emits at the end of the stream.
        """
        self._last_stream_usage = None
        stream_input_tokens = 0
        stream_output_tokens = 0
        stream_model = self.model

        system_blocks, formatted_messages = self._format_messages(messages)

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system_blocks:
            payload["system"] = system_blocks

        assert self.api_key is not None
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=self._headers(self.api_key),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        try:
                            event = json.loads(data)
                            event_type = event.get("type", "")

                            # message_start carries the model and input
                            # token count
                            if event_type == "message_start":
                                msg = event.get("message", {})
                                stream_model = msg.get("model", self.model)
                                usage = msg.get("usage", {})
                                stream_input_tokens = usage.get("input_tokens", 0)

                            # content_block_delta carries text chunks
                            elif event_type == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")

                            # message_delta at end carries output token count
                            elif event_type == "message_delta":
                                usage = event.get("usage", {})
                                stream_output_tokens = usage.get("output_tokens", 0)

                        except json.JSONDecodeError:
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
