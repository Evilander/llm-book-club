"""Align contiguous quotations to original Unicode code-point offsets."""
import re
import unicodedata

import regex


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def grapheme_boundaries(text: str) -> set[int]:
    return {0, *(cluster.end() for cluster in regex.finditer(r"\X", text))}


def _normalized_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Keep combining sequences and normalization expansions in one source span."""
    characters: list[str] = []
    spans: list[tuple[int, int]] = []
    for cluster in regex.finditer(r"\X", text):
        for character in unicodedata.normalize("NFKC", cluster.group()).casefold():
            if character.isspace():
                if not characters:
                    continue
                if characters[-1] == " ":
                    spans[-1] = (spans[-1][0], cluster.end())
                    continue
                character = " "
            characters.append(character)
            spans.append((cluster.start(), cluster.end()))
    if characters and characters[-1] == " ":
        characters.pop()
        spans.pop()
    return "".join(characters), spans


def compute_span_alignment(chunk_text: str, quote: str) -> tuple[int, int, str] | None:
    """Return a real, contiguous source span; normalization never changes words."""
    if not chunk_text or not quote or not quote.strip():
        return None
    boundaries = grapheme_boundaries(chunk_text)
    index = chunk_text.find(quote)
    while index >= 0:
        if index in boundaries and index + len(quote) in boundaries:
            return index, index + len(quote), "exact"
        index = chunk_text.find(quote, index + 1)
    normalized, spans = _normalized_map(chunk_text)
    target = normalize_text(quote)
    if not target:
        return None
    index = normalized.find(target)
    while index >= 0:
        start, end = spans[index][0], spans[index + len(target) - 1][1]
        # In particular, do not accept half of a ligature or a misaligned
        # combining sequence. The returned original slice must prove the match.
        if normalize_text(chunk_text[start:end]) == target:
            return start, end, "normalized"
        index = normalized.find(target, index + 1)
    return None
