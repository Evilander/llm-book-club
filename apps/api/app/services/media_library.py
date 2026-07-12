from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_DISCUSSION_EXTENSIONS = {
    ".pdf",
    ".epub",
    ".txt",
    ".fb2",
    ".mobi",
    ".azw",
    ".azw3",
    ".prc",
}
SUPPORTED_REFLOWABLE_EXTENSIONS = {
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".prc",
    ".fb2",
}
SUPPORTED_COMIC_EXTENSIONS = {".cbz"}
SUPPORTED_READER_EXTENSIONS = (
    SUPPORTED_DISCUSSION_EXTENSIONS
    | SUPPORTED_REFLOWABLE_EXTENSIONS
    | SUPPORTED_COMIC_EXTENSIONS
)
SUPPORTED_AUDIOBOOK_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".aac", ".flac", ".ogg", ".wav"}

CATALOG_VERSION = 2
_catalog_lock = threading.RLock()
_catalog_memory: dict[str, dict[str, Any]] = {}
_catalog_indexes: dict[str, dict[str, dict[str, Any]]] = {}

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


def format_family(extension: str) -> str:
    """Return the reader-facing format family for an extension."""
    extension = extension.lower().lstrip(".")
    if extension == "epub":
        return "epub"
    if extension == "pdf":
        return "pdf"
    if extension == "txt":
        return "text"
    if extension in {"mobi", "azw", "azw3", "prc", "fb2"}:
        return "kindle"
    if extension == "cbz":
        return "comic"
    if f".{extension}" in SUPPORTED_AUDIOBOOK_EXTENSIONS:
        return "audio"
    return "other"


def reader_kind(extension: str) -> str | None:
    """Return the frontend renderer needed for a local publication."""
    extension = extension.lower().lstrip(".")
    if extension == "pdf":
        return "pdf"
    if extension == "txt":
        return "text"
    if f".{extension}" in (SUPPORTED_REFLOWABLE_EXTENSIONS | SUPPORTED_COMIC_EXTENSIONS):
        return "foliate"
    if f".{extension}" in SUPPORTED_AUDIOBOOK_EXTENSIONS:
        return "audio"
    return None


def media_id_for_path(root_path: Path, path: Path) -> str:
    """Build a stable, non-reversible id from the root-relative path."""
    try:
        relative = path.relative_to(root_path)
    except ValueError:
        relative = path
    normalized = relative.as_posix().casefold().encode("utf-8", errors="surrogatepass")
    return hashlib.blake2s(normalized, digest_size=12).hexdigest()


def _empty_catalog(root_dir: str | None, extensions: set[str]) -> dict[str, Any]:
    return {
        "version": CATALOG_VERSION,
        "root": root_dir or "",
        "extensions": sorted(extensions),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "scan_duration_ms": 0,
        "items": [],
    }


def _catalog_key(root_dir: str, extensions: set[str]) -> str:
    return f"{Path(root_dir).resolve()}|{'|'.join(sorted(extensions))}"


def _read_catalog_cache(
    cache_file: Path,
    *,
    resolved_root: Path,
    extensions: set[str],
    ttl_seconds: int,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if payload.get("version") != CATALOG_VERSION:
            return None
        if Path(payload.get("root", "")).resolve() != resolved_root:
            return None
        if payload.get("extensions") != sorted(extensions):
            return None
        indexed_at = datetime.fromisoformat(payload["indexed_at"])
        if indexed_at.tzinfo is None:
            indexed_at = indexed_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - indexed_at).total_seconds()
        if age_seconds > max(0, ttl_seconds):
            return None
        if not isinstance(payload.get("items"), list):
            return None
        return payload
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _write_catalog_cache(cache_file: Path, payload: dict[str, Any]) -> None:
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_file.with_name(
            f".{cache_file.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, cache_file)
    except OSError:
        # The catalog is a performance cache. A read-only storage directory
        # must not make the library itself unavailable.
        return


def get_media_catalog(
    root_dir: str | None,
    *,
    extensions: set[str],
    minimum_bytes: int = 1024,
    cache_file: str | Path | None = None,
    ttl_seconds: int = 24 * 60 * 60,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return a durable snapshot of a media directory.

    Large personal libraries should be walked once, not on every keystroke in
    the search box. The snapshot is kept in memory and, when ``cache_file`` is
    provided, persisted across API restarts. Callers can explicitly refresh it
    after adding or removing books.
    """
    if not root_dir:
        return _empty_catalog(root_dir, extensions)

    root_path = Path(root_dir)
    if not root_path.exists():
        return _empty_catalog(root_dir, extensions)

    resolved_root = root_path.resolve()
    key = _catalog_key(str(resolved_root), extensions)
    cache_path = Path(cache_file) if cache_file else None

    with _catalog_lock:
        if not force_refresh:
            in_memory = _catalog_memory.get(key)
            if in_memory:
                try:
                    indexed_at = datetime.fromisoformat(in_memory["indexed_at"])
                    if indexed_at.tzinfo is None:
                        indexed_at = indexed_at.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - indexed_at).total_seconds()
                    if age <= max(0, ttl_seconds):
                        return in_memory
                except (ValueError, TypeError, KeyError):
                    pass

            if cache_path:
                persisted = _read_catalog_cache(
                    cache_path,
                    resolved_root=resolved_root,
                    extensions=extensions,
                    ttl_seconds=ttl_seconds,
                )
                if persisted:
                    _catalog_memory[key] = persisted
                    return persisted

        started = time.perf_counter()
        items = scan_media_dir(
            str(resolved_root),
            extensions=extensions,
            minimum_bytes=minimum_bytes,
        )
        payload = {
            "version": CATALOG_VERSION,
            "root": str(resolved_root),
            "extensions": sorted(extensions),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "scan_duration_ms": round((time.perf_counter() - started) * 1000),
            "items": items,
        }
        _catalog_memory[key] = payload
        if cache_path:
            _write_catalog_cache(cache_path, payload)
        return payload


def clear_media_catalog_memory() -> None:
    """Clear process-local snapshots (primarily useful in tests)."""
    with _catalog_lock:
        _catalog_memory.clear()
        _catalog_indexes.clear()


def find_media_catalog_item(
    catalog: dict[str, Any],
    media_id: str,
) -> dict[str, Any] | None:
    """Resolve a stable media id without rebuilding a 36k-item map per request."""
    index_key = f"{catalog.get('root', '')}|{catalog.get('indexed_at', '')}"
    with _catalog_lock:
        index = _catalog_indexes.get(index_key)
        if index is None:
            index = {item["id"]: item for item in catalog.get("items", [])}
            _catalog_indexes.clear()
            _catalog_indexes[index_key] = index
        return index.get(media_id)


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
    """Recursively scan a directory for supported media files."""
    if not root_dir or not Path(root_dir).exists():
        return []
    return _walk_media_dir(
        Path(root_dir).resolve(),
        extensions=extensions,
        minimum_bytes=minimum_bytes,
    )


def _walk_media_dir(
    root_path: Path,
    *,
    extensions: set[str],
    minimum_bytes: int,
) -> list[dict]:
    """Perform the actual filesystem walk for a media catalog."""

    results: list[dict] = []
    for root, _dirs, files in os.walk(root_path):
        for filename in files:
            path = Path(root) / filename
            extension = path.suffix.lower()
            if extension not in extensions:
                continue

            try:
                stat = path.stat()
                size_bytes = stat.st_size
            except OSError:
                continue

            if size_bytes < minimum_bytes:
                continue

            ext = extension.lstrip(".")
            kind = reader_kind(ext)
            results.append({
                "id": media_id_for_path(root_path, path),
                "path": str(path),
                "filename": filename,
                "extension": ext,
                "format_family": format_family(ext),
                "reader_kind": kind,
                "can_discuss": extension in SUPPORTED_DISCUSSION_EXTENSIONS,
                "size_bytes": size_bytes,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "title_guess": guess_title(filename),
                "parent_folder": path.parent.name,
            })

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
