"""Chunk text sections into smaller pieces for embedding and retrieval."""
from __future__ import annotations
import re
from dataclasses import dataclass

from .extractor import ExtractedSection


@dataclass
class TextChunk:
    """A chunk of text with position information."""
    text: str
    char_start: int  # relative to section
    char_end: int
    absolute_char_start: int  # relative to full book
    absolute_char_end: int
    order_index: int
    source_ref: str | None = None  # page number or location


@dataclass
class ChunkedSection:
    """A section broken into chunks."""
    section: ExtractedSection
    chunks: list[TextChunk]


# Target chunk size in characters (roughly 500-800 tokens)
DEFAULT_CHUNK_SIZE = 1500
# Overlap between chunks
DEFAULT_OVERLAP = 200
# Minimum chunk size (don't create tiny trailing chunks)
MIN_CHUNK_SIZE = 200


def _find_break_point(text: str, target: int, window: int = 200) -> int:
    """
    Find a good break point near the target position.
    Prefers paragraph breaks > sentence breaks > word breaks.
    """
    start = max(0, target - window)
    end = min(len(text), target + window)
    search_region = text[start:end]

    # Look for paragraph break (double newline)
    para_breaks = [m.end() for m in re.finditer(r"\n\n+", search_region)]
    if para_breaks:
        # Find closest to target
        closest = min(para_breaks, key=lambda x: abs((start + x) - target))
        return start + closest

    # Look for sentence break
    sentence_breaks = [m.end() for m in re.finditer(r"[.!?]\s+", search_region)]
    if sentence_breaks:
        closest = min(sentence_breaks, key=lambda x: abs((start + x) - target))
        return start + closest

    # Look for word break
    word_breaks = [m.end() for m in re.finditer(r"\s+", search_region)]
    if word_breaks:
        closest = min(word_breaks, key=lambda x: abs((start + x) - target))
        return start + closest

    # Fall back to target position
    return target


def chunk_text(
    text: str,
    section_char_start: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    source_ref_base: str | None = None,
) -> list[TextChunk]:
    """
    Split text into overlapping chunks with position tracking.

    Args:
        text: The text to chunk
        section_char_start: Absolute character position of section start
        chunk_size: Target chunk size in characters
        overlap: Number of characters to overlap between chunks
        source_ref_base: Base source reference (e.g., page number)

    Returns:
        List of TextChunk objects
    """
    if len(text) <= chunk_size:
        return [
            TextChunk(
                text=text.strip(),
                char_start=0,
                char_end=len(text),
                absolute_char_start=section_char_start,
                absolute_char_end=section_char_start + len(text),
                order_index=0,
                source_ref=source_ref_base,
            )
        ]

    chunks = []
    pos = 0
    chunk_idx = 0

    while pos < len(text):
        # Calculate end position
        end_target = pos + chunk_size

        if end_target >= len(text):
            # Last chunk - take everything remaining
            end_pos = len(text)
        else:
            # Find a good break point
            end_pos = _find_break_point(text, end_target)

        chunk_text_content = text[pos:end_pos].strip()

        if len(chunk_text_content) >= MIN_CHUNK_SIZE or not chunks:
            chunks.append(
                TextChunk(
                    text=chunk_text_content,
                    char_start=pos,
                    char_end=end_pos,
                    absolute_char_start=section_char_start + pos,
                    absolute_char_end=section_char_start + end_pos,
                    order_index=chunk_idx,
                    source_ref=source_ref_base,
                )
            )
            chunk_idx += 1

        # Move to next chunk position (with overlap)
        pos = end_pos - overlap
        if pos <= chunks[-1].char_start if chunks else 0:
            # Avoid infinite loop if overlap is larger than progress
            pos = end_pos

        if end_pos >= len(text):
            break

    return chunks


def chunk_sections(
    sections: list[ExtractedSection],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ChunkedSection]:
    """
    Chunk all sections of a book.

    Args:
        sections: List of extracted sections
        chunk_size: Target chunk size in characters
        overlap: Number of characters to overlap

    Returns:
        List of ChunkedSection objects
    """
    result = []

    for section in sections:
        # Build source reference
        source_ref = None
        if section.page_start:
            if section.page_end and section.page_end != section.page_start:
                source_ref = f"pp. {section.page_start}-{section.page_end}"
            else:
                source_ref = f"p. {section.page_start}"

        chunks = chunk_text(
            text=section.text,
            section_char_start=section.char_start,
            chunk_size=chunk_size,
            overlap=overlap,
            source_ref_base=source_ref,
        )

        result.append(ChunkedSection(section=section, chunks=chunks))

    return result


def estimate_tokens(text: str) -> int:
    """
    Roughly estimate token count for text.
    Uses ~4 characters per token as approximation.
    """
    return len(text) // 4


def estimate_reading_time(text: str, wpm: int = 250) -> int:
    """
    Estimate reading time in minutes.
    Average adult reading speed is ~250 words per minute.
    """
    word_count = len(text.split())
    return max(1, round(word_count / wpm))
