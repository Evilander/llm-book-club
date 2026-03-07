from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, AsyncIterator


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
