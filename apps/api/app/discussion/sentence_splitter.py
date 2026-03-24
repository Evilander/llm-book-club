"""Sentence-level text splitter for streaming TTS pipelining.

Buffers text deltas and emits complete sentences as soon as they're
detected. This allows the frontend to fire TTS requests sentence-by-
sentence instead of waiting for the full agent response.
"""
from __future__ import annotations

import re

# Abbreviations that end with a period but don't end a sentence
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "blvd",
    "vol", "ch", "pt", "pg", "pp", "ed", "etc", "vs", "al", "fig",
    "approx", "dept", "est", "govt", "inc", "ltd", "no", "rev",
})

# Pattern: sentence-ending punctuation followed by whitespace or end of string
_SENTENCE_END = re.compile(
    r'([.!?…]+)'           # sentence-ending punctuation
    r'[\"\'\)\]]*'         # optional closing quotes/brackets
    r'(?:\s|$)'            # whitespace or end of string
)


class SentenceSplitter:
    """Streaming sentence splitter that buffers text and yields complete sentences.

    Usage::

        splitter = SentenceSplitter()
        for delta in text_deltas:
            for sentence in splitter.feed(delta):
                # sentence is a complete sentence ready for TTS
                yield sentence
        # Flush any remaining text
        remainder = splitter.flush()
        if remainder:
            yield remainder
    """

    def __init__(self, min_length: int = 20, max_length: int = 300):
        """
        Args:
            min_length: Minimum characters before emitting a sentence.
                        Prevents tiny fragments like "OK." from firing TTS.
            max_length: Maximum buffer size before force-emitting.
                        Prevents unbounded buffering on long run-on sentences.
        """
        self._buffer = ""
        self._min_length = min_length
        self._max_length = max_length
        self._sentence_index = 0

    @property
    def sentence_index(self) -> int:
        return self._sentence_index

    def feed(self, delta: str) -> list[str]:
        """Feed a text delta and return any complete sentences.

        Returns a list of 0 or more complete sentences.
        """
        self._buffer += delta
        sentences: list[str] = []

        while True:
            sentence = self._try_extract()
            if sentence is None:
                break
            sentences.append(sentence)
            self._sentence_index += 1

        return sentences

    def flush(self) -> str | None:
        """Flush any remaining buffered text as a final sentence.

        Returns the remaining text, or None if the buffer is empty.
        """
        text = self._buffer.strip()
        self._buffer = ""
        if text:
            self._sentence_index += 1
            return text
        return None

    def _try_extract(self) -> str | None:
        """Try to extract a complete sentence from the buffer."""
        # Force-emit if buffer is very long (run-on sentence protection)
        if len(self._buffer) >= self._max_length:
            return self._force_break()

        # Look for sentence-ending punctuation
        match = _SENTENCE_END.search(self._buffer)
        if match is None:
            return None

        end_pos = match.end()
        candidate = self._buffer[:end_pos].strip()

        # Check if this is actually an abbreviation, not a sentence end
        if self._is_abbreviation(candidate, match):
            # Look for next potential sentence end after this one
            next_match = _SENTENCE_END.search(self._buffer, pos=match.end())
            if next_match is None:
                return None
            end_pos = next_match.end()
            candidate = self._buffer[:end_pos].strip()

        # Don't emit tiny fragments
        if len(candidate) < self._min_length:
            return None

        self._buffer = self._buffer[end_pos:]
        return candidate

    def _is_abbreviation(self, text: str, match: re.Match) -> bool:
        """Check if the period at the match position is part of an abbreviation."""
        punct = match.group(1)
        if punct != ".":
            return False

        # Find the word before the period
        before = text[:match.start()].rstrip()
        if not before:
            return False

        # Extract last word
        words = before.split()
        if not words:
            return False

        last_word = words[-1].strip("\"'([{").lower()
        return last_word in _ABBREVIATIONS

    def _force_break(self) -> str | None:
        """Force a break at the best available position."""
        # Try to break at a comma, semicolon, or dash
        for sep in [", ", "; ", " — ", " – ", " - "]:
            idx = self._buffer.rfind(sep, 0, self._max_length)
            if idx > self._min_length:
                text = self._buffer[:idx + len(sep)].strip()
                self._buffer = self._buffer[idx + len(sep):]
                return text

        # Fall back to breaking at last space
        idx = self._buffer.rfind(" ", self._min_length, self._max_length)
        if idx > 0:
            text = self._buffer[:idx].strip()
            self._buffer = self._buffer[idx + 1:]
            return text

        # Last resort: emit the whole buffer
        text = self._buffer[:self._max_length].strip()
        self._buffer = self._buffer[self._max_length:]
        return text if text else None
