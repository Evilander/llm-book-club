from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol


# Sentinel marker inserted between the stable agent system prefix and any
# per-turn retrieval evidence. Providers that support prompt caching
# (AnthropicClient) split the system string on this marker so the stable
# prefix can be cached across turns while evidence varies. Callers that
# don't split on it see it as harmless text.
EVIDENCE_CACHE_BOUNDARY = "<<<__EVIDENCE_CACHE_BOUNDARY__>>>"


@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM provider, wrapping content with usage metadata.

    Designed to be backward-compatible: ``str(response)`` returns the content
    string, so callers that only need text can treat it as a string-like value.
    """
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    def __str__(self) -> str:
        return self.content

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class StructuredOutputError(ValueError):
    """Raised when a provider does not return a usable JSON object."""


@dataclass
class StructuredLLMResponse:
    """Schema-constrained provider response with usage and refusal state."""

    content: str
    parsed: dict[str, Any] | None
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    refusal: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def parse_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object, accepting an optional Markdown code fence."""
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError) as exc:
        raise StructuredOutputError("Provider returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise StructuredOutputError("Provider structured output must be a JSON object")
    return parsed


class LLMClient(Protocol):
    """Protocol for LLM providers."""

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            The assistant's response text
        """
        ...

    async def complete_with_usage(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Generate a completion and return content together with token usage.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with content text and input/output token counts
        """
        ...

    async def complete_structured(
        self,
        messages: list[LLMMessage],
        *,
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> StructuredLLMResponse:
        """Generate one JSON object constrained by ``json_schema``."""
        ...

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Stream a completion for the given messages.

        Args:
            messages: List of conversation messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Chunks of the assistant's response
        """
        ...

    @property
    def last_stream_usage(self) -> LLMResponse | None:
        """
        Token usage from the most recent ``stream()`` call.

        Populated after the stream is fully consumed. Returns None if no
        stream has been consumed yet or the provider does not report
        streaming usage.
        """
        ...
