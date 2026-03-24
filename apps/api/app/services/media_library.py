from __future__ import annotations

import os
import re
from pathlib import Path


SUPPORTED_BOOK_EXTENSIONS = {".pdf", ".epub", ".txt"}
SUPPORTED_AUDIOBOOK_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".aac", ".flac", ".ogg", ".wav"}

_NOISE_WORDS = {
    "a",
    "an",
    "and",
    "the",
    "audiobook",
    "audio",
    "book",
    "books",
    "unabridged",
    "abridged",
    "retail",
    "digital",
    "edition",
    "series",
    "part",
    "vol",
    "volume",
    "narrated",
    "read",
    "by",
    "disc",
    "cd",
}


def guess_title(filename: str) -> str:
    """Guess a clean human-readable title from a filename."""
    stem = Path(filename).stem
    stem = re.sub(r"[\[\(\{].*?[\]\)\}]", " ", stem)
    stem = re.sub(r"[_\-\.]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or filename


def tokenize_media_name(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[\[\(\{].*?[\]\)\}]", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    tokens = [
        token
        for token in normalized.split()
        if len(token) > 1 and token not in _NOISE_WORDS and not token.isdigit()
    ]
    return tokens


def scan_media_dir(
    root_dir: str | None,
    *,
    extensions: set[str],
    minimum_bytes: int = 1024,
) -> list[dict]:
    """Recursively scan a directory for media files."""
    if not root_dir:
        return []

    root_path = Path(root_dir)
    if not root_path.exists():
        return []

    results: list[dict] = []
    for root, _dirs, files in os.walk(root_path):
        for filename in files:
            path = Path(root) / filename
            extension = path.suffix.lower()
            if extension not in extensions:
                continue

            try:
                size_bytes = path.stat().st_size
            except OSError:
                continue

            if size_bytes < minimum_bytes:
                continue

            results.append(
                {
                    "path": str(path),
                    "filename": filename,
                    "extension": extension.lstrip("."),
                    "size_bytes": size_bytes,
                    "title_guess": guess_title(filename),
                    "parent_folder": path.parent.name,
                }
            )

    results.sort(key=lambda item: item["filename"].lower())
    return results


def score_audiobook_match(
    *,
    book_title: str,
    book_author: str | None,
    candidate_title: str,
    candidate_parent: str | None = None,
) -> tuple[float, str]:
    """Return a rough [0,1] match score and an explanation string."""
    title_tokens = set(tokenize_media_name(book_title))
    author_tokens = set(tokenize_media_name(book_author))
    candidate_tokens = set(tokenize_media_name(candidate_title))
    parent_tokens = set(tokenize_media_name(candidate_parent))

    if not title_tokens or not candidate_tokens:
        return 0.0, "insufficient metadata"

    title_overlap = len(title_tokens & candidate_tokens) / len(title_tokens)
    parent_overlap = len(title_tokens & parent_tokens) / len(title_tokens) if parent_tokens else 0.0
    author_overlap = (
        len(author_tokens & (candidate_tokens | parent_tokens)) / len(author_tokens)
        if author_tokens
        else 0.0
    )

    book_slug = " ".join(tokenize_media_name(book_title))
    candidate_slug = " ".join(tokenize_media_name(candidate_title))
    exactish = 0.15 if book_slug and book_slug in candidate_slug else 0.0

    score = min(1.0, title_overlap * 0.7 + parent_overlap * 0.1 + author_overlap * 0.2 + exactish)

    if score >= 0.9:
        reason = "title and author match strongly"
    elif score >= 0.7:
        reason = "title tokens align well"
    elif score >= 0.45:
        reason = "partial title overlap"
    else:
        reason = "weak candidate"

    return score, reason


def match_audiobooks_for_book(
    *,
    book_title: str,
    book_author: str | None,
    audiobook_entries: list[dict],
    limit: int = 3,
) -> list[dict]:
    scored: list[dict] = []
    for entry in audiobook_entries:
        score, reason = score_audiobook_match(
            book_title=book_title,
            book_author=book_author,
            candidate_title=entry.get("title_guess", ""),
            candidate_parent=entry.get("parent_folder"),
        )
        if score < 0.35:
            continue
        scored.append(
            {
                **entry,
                "match_score": round(score, 3),
                "match_reason": reason,
            }
        )

    scored.sort(key=lambda item: (-item["match_score"], item["filename"].lower()))
    return scored[:limit]
