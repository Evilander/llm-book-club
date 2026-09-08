"""A continuous reading edition of overlapping retrieval chunks.

Offsets here address the assembled reading text, not the extraction's source
coordinates. Chunk mappings preserve the link back to verified local citations.
"""
from dataclasses import dataclass
from typing import Protocol


class TextChunk(Protocol):
    id: str
    section_id: str
    text: str
    char_start: int
    char_end: int


@dataclass
class ReadingText:
    text: str
    chunks: list[dict]


def assemble_reading_text(chunks: list[TextChunk]) -> ReadingText:
    text = ""
    spans = []
    previous = None
    for chunk in chunks:
        if not chunk.text:
            continue
        start = len(text)
        if previous is not None:
            expected_overlap = max(0, previous.char_end - chunk.char_start) if previous.section_id == chunk.section_id else 0
            matched = False
            if expected_overlap:
                # Ingestion historically stripped edge whitespace without adjusting
                # source offsets. Match actual text, never assume offset arithmetic.
                window_start = max(0, len(text) - expected_overlap - 80)
                # The overlap can be shorter than a fixed search prefix. Find
                # the longest real suffix/prefix match, including short chunks.
                for overlap in range(min(len(text) - window_start, len(chunk.text)), 0, -1):
                    if text.endswith(chunk.text[:overlap]):
                        start = len(text) - overlap
                        text += chunk.text[overlap:]
                        matched = True
                        break
            if not matched:
                separator = "\n\n" if previous.section_id != chunk.section_id else " "
                text += separator
                start = len(text)
                text += chunk.text
        else:
            text = chunk.text
        spans.append({"chunk_id": str(chunk.id), "section_id": str(chunk.section_id), "char_start": start, "char_end": start + len(chunk.text)})
        previous = chunk
    return ReadingText(text, spans)


def page_bounds(text: str, page: int, page_size: int) -> tuple[int, int]:
    def boundary(target: int) -> int:
        if target <= 0:
            return 0
        if target >= len(text):
            return len(text)
        if text[target - 1].isspace() or text[target].isspace():
            return target
        last_space = text.rfind(" ", max(0, target - min(120, page_size // 2)), target)
        return last_space + 1 if last_space >= 0 else target
    return boundary((page - 1) * page_size), boundary(page * page_size)
