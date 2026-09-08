from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path, PureWindowsPath

from ..settings import settings


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

_SCAN_CACHE: dict[tuple[str, tuple[str, ...], int], tuple[float, list[dict]]] = {}
_SCAN_CACHE_LOCK = threading.Lock()
ROOT_FOLDER_SENTINEL = "__root__"


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


def top_level_parent_folder(root_path: Path, file_path: Path) -> str | None:
    try:
        relative = file_path.relative_to(root_path)
    except ValueError:
        try:
            relative = file_path.resolve().relative_to(root_path.resolve())
        except (OSError, RuntimeError, ValueError):
            return file_path.parent.name or None

    return relative.parts[0] if len(relative.parts) > 1 else None


def scan_media_dir(
    root_dir: str | None,
    *,
    extensions: set[str],
    minimum_bytes: int = 1024,
    refresh: bool = False,
) -> list[dict]:
    """Recursively scan a directory for media files."""
    if not root_dir:
        return []

    root_path = Path(root_dir)
    if not root_path.exists():
        return []

    resolved_root = str(root_path.resolve())
    cache_key = (resolved_root, tuple(sorted(extensions)), minimum_bytes)
    cache_ttl = max(0, settings.library_scan_cache_ttl_sec)

    if not refresh and cache_ttl > 0:
        with _SCAN_CACHE_LOCK:
            cached = _SCAN_CACHE.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < cache_ttl:
            return list(cached[1])

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
                    "parent_folder": top_level_parent_folder(root_path, path),
                }
            )

    results.sort(key=lambda item: item["filename"].lower())

    if cache_ttl > 0:
        with _SCAN_CACHE_LOCK:
            _SCAN_CACHE[cache_key] = (time.monotonic(), results)

    return results


def clear_scan_cache() -> None:
    with _SCAN_CACHE_LOCK:
        _SCAN_CACHE.clear()


def summarize_media_folders(
    *,
    books_dir: str,
    book_entries: list[dict],
    audiobook_entries: list[dict] | None = None,
) -> dict:
    folders: dict[str, dict] = {}
    root_book_count = 0
    # Imported catalog paths retain their source platform’s separators.
    root_path = PureWindowsPath(books_dir) if PureWindowsPath(books_dir).is_absolute() else Path(books_dir)

    for entry in book_entries:
        folder = entry.get("parent_folder")
        if not folder:
            root_book_count += 1
            continue
        folder_data = folders.setdefault(
            folder,
            {
                "name": folder,
                "path": str(root_path / folder),
                "book_count": 0,
                "audiobook_count": 0,
                "sample_titles": [],
            },
        )
        folder_data["book_count"] += 1
        if len(folder_data["sample_titles"]) < 3:
            folder_data["sample_titles"].append(entry["filename"])

    for entry in audiobook_entries or []:
        folder = entry.get("parent_folder")
        if not folder or folder not in folders:
            continue
        folders[folder]["audiobook_count"] += 1

    ordered_folders = sorted(
        folders.values(),
        key=lambda item: (-item["book_count"], item["name"].lower()),
    )
    return {
        "books_dir": books_dir,
        "total_books": len(book_entries),
        "folders": ordered_folders,
        "root_book_count": root_book_count,
    }


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
