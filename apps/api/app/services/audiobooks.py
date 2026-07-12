from __future__ import annotations

import re
import threading
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile, MutagenError
from mutagen.id3 import ID3

from .media_library import guess_title, media_id_for_path, score_audiobook_match


_manifest_lock = threading.RLock()
_manifest_cache: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
_cover_cache: OrderedDict[str, tuple[str, tuple[bytes, str] | None]] = OrderedDict()
_group_cache: dict[str, list[dict[str, Any]]] = {}
_MAX_MANIFEST_CACHE_ENTRIES = 32
_MAX_COVER_CACHE_ENTRIES = 8
_MAX_COVER_BYTES = 12 * 1024 * 1024


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )


def _group_source(root: Path, entry: dict[str, Any]) -> Path:
    path = Path(entry["path"])
    return path if path.parent.resolve() == root else path.parent


def group_audiobook_entries(
    root_dir: str,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group multi-track folders while keeping root-level files independent."""
    root = Path(root_dir).resolve()
    grouped: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[_group_source(root, entry)].append(entry)

    audiobooks: list[dict[str, Any]] = []
    for source, tracks in grouped.items():
        tracks.sort(key=lambda item: _natural_key(item["filename"]))
        is_folder = source.is_dir() or len(tracks) > 1
        extensions = sorted({track["extension"] for track in tracks})
        title = (
            re.sub(r"[_.]+", " ", source.name).strip()
            if is_folder
            else guess_title(tracks[0]["filename"])
        )
        modified_at = max(
            (track.get("modified_at") or "" for track in tracks),
            default="",
        )
        audiobooks.append(
            {
                "id": media_id_for_path(root, source),
                "title": title,
                "title_guess": title,
                "source_path": str(source),
                "path": str(source),
                "source_kind": "folder" if is_folder else "file",
                "filename": source.name if is_folder else tracks[0]["filename"],
                "extension": extensions[0] if len(extensions) == 1 else "audio",
                "extensions": extensions,
                "size_bytes": sum(int(track["size_bytes"]) for track in tracks),
                "track_count": len(tracks),
                "parent_folder": source.parent.name if source != root else None,
                "modified_at": modified_at or None,
                "_tracks": tracks,
            }
        )

    audiobooks.sort(key=lambda item: _natural_key(item["title"]))
    return audiobooks


def grouped_audiobook_catalog(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    cache_key = f"{catalog.get('root', '')}|{catalog.get('indexed_at', '')}"
    with _manifest_lock:
        cached = _group_cache.get(cache_key)
        if cached is not None:
            return cached
    grouped = group_audiobook_entries(catalog["root"], catalog.get("items", []))
    with _manifest_lock:
        _group_cache.clear()
        _group_cache[cache_key] = grouped
    return grouped


def audiobook_summary(audiobook: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in audiobook.items() if not key.startswith("_")}


def find_audiobook(
    audiobooks: list[dict[str, Any]],
    audiobook_id: str,
) -> dict[str, Any] | None:
    return next((item for item in audiobooks if item["id"] == audiobook_id), None)


def search_audiobooks(
    audiobooks: list[dict[str, Any]],
    query: str | None,
) -> list[dict[str, Any]]:
    if not query:
        return audiobooks
    terms = query.casefold().split()
    return [
        audiobook
        for audiobook in audiobooks
        if all(
            term
            in " ".join(
                [
                    audiobook["title"],
                    audiobook.get("parent_folder") or "",
                    audiobook.get("source_path") or "",
                ]
            ).casefold()
            for term in terms
        )
    ]


def match_audiobook_groups(
    *,
    book_title: str,
    book_author: str | None,
    audiobooks: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for audiobook in audiobooks:
        score, reason = score_audiobook_match(
            book_title=book_title,
            book_author=book_author,
            candidate_title=audiobook["title"],
            candidate_parent=" ".join(
                filter(
                    None,
                    [
                        audiobook.get("parent_folder"),
                        audiobook.get("source_path"),
                    ],
                )
            ),
        )
        if score < 0.35:
            continue
        matches.append(
            {
                **audiobook_summary(audiobook),
                "match_score": round(score, 3),
                "match_reason": reason,
            }
        )
    matches.sort(key=lambda item: (-item["match_score"], _natural_key(item["title"])))
    return matches[:limit]


def _first_tag(tags: Any, *keys: str) -> str | None:
    if not tags:
        return None
    for key in keys:
        value = tags.get(key)
        if isinstance(value, (list, tuple)) and value:
            text = str(value[0]).strip()
        elif value is not None:
            text = str(value).strip()
        else:
            continue
        if text:
            return text
    return None


def _track_metadata(entry: dict[str, Any], index: int) -> dict[str, Any]:
    title = guess_title(entry["filename"])
    album = None
    artist = None
    duration = None
    try:
        audio = MutagenFile(entry["path"], easy=True)
        if audio is not None:
            title = _first_tag(audio.tags, "title") or title
            album = _first_tag(audio.tags, "album")
            artist = _first_tag(audio.tags, "artist", "albumartist", "composer")
            length = getattr(getattr(audio, "info", None), "length", None)
            if length is not None and float(length) >= 0:
                duration = round(float(length), 3)
    except (MutagenError, OSError, ValueError, TypeError):
        pass
    return {
        "id": entry["id"],
        "index": index,
        "title": title,
        "album": album,
        "artist": artist,
        "filename": entry["filename"],
        "extension": entry["extension"],
        "size_bytes": entry["size_bytes"],
        "duration_seconds": duration,
    }


def _manifest_signature(audiobook: dict[str, Any]) -> str:
    return "|".join(
        f"{track['id']}:{track['size_bytes']}:{track.get('modified_at', '')}"
        for track in audiobook["_tracks"]
    )


def build_audiobook_manifest(audiobook: dict[str, Any]) -> dict[str, Any]:
    signature = _manifest_signature(audiobook)
    audiobook_id = audiobook["id"]
    with _manifest_lock:
        cached = _manifest_cache.get(audiobook_id)
        if cached and cached[0] == signature:
            _manifest_cache.move_to_end(audiobook_id)
            return cached[1]

    tracks = [
        _track_metadata(entry, index)
        for index, entry in enumerate(audiobook["_tracks"])
    ]
    albums = Counter(track["album"] for track in tracks if track["album"])
    artists = Counter(track["artist"] for track in tracks if track["artist"])
    durations = [
        track["duration_seconds"]
        for track in tracks
        if track["duration_seconds"] is not None
    ]
    manifest = {
        **audiobook_summary(audiobook),
        "title": albums.most_common(1)[0][0] if albums else audiobook["title"],
        "author": artists.most_common(1)[0][0] if artists else None,
        "duration_seconds": round(sum(durations), 3) if len(durations) == len(tracks) else None,
        "tracks": tracks,
    }

    with _manifest_lock:
        _manifest_cache[audiobook_id] = (signature, manifest)
        _manifest_cache.move_to_end(audiobook_id)
        while len(_manifest_cache) > _MAX_MANIFEST_CACHE_ENTRIES:
            _manifest_cache.popitem(last=False)
    return manifest


def find_manifest_track(
    audiobook: dict[str, Any],
    track_id: str,
) -> dict[str, Any] | None:
    return next(
        (track for track in audiobook["_tracks"] if track["id"] == track_id),
        None,
    )


def _cover_media_type(cover_bytes: bytes, declared: str | None = None) -> str:
    if declared and declared.startswith("image/"):
        return declared
    if cover_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if cover_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if cover_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if cover_bytes.startswith(b"RIFF") and cover_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _cover_from_track(path: str) -> tuple[bytes, str] | None:
    try:
        if Path(path).suffix.casefold() == ".mp3":
            tags = ID3(path)
            for frame in tags.values():
                cover_bytes = getattr(frame, "data", None)
                if cover_bytes:
                    return bytes(cover_bytes), _cover_media_type(
                        bytes(cover_bytes), getattr(frame, "mime", None)
                    )

        audio = MutagenFile(path)
        if audio is None:
            return None
        pictures = getattr(audio, "pictures", None)
        if pictures:
            picture = pictures[0]
            return bytes(picture.data), _cover_media_type(
                bytes(picture.data), getattr(picture, "mime", None)
            )
        tags = getattr(audio, "tags", None)
        covers = tags.get("covr") if tags else None
        if covers:
            cover_bytes = bytes(covers[0])
            image_format = getattr(covers[0], "imageformat", None)
            declared = "image/png" if image_format == 14 else "image/jpeg" if image_format == 13 else None
            return cover_bytes, _cover_media_type(cover_bytes, declared)
    except (MutagenError, OSError, ValueError, TypeError):
        return None
    return None


def extract_audiobook_cover(audiobook: dict[str, Any]) -> tuple[bytes, str] | None:
    audiobook_id = audiobook["id"]
    signature = _manifest_signature(audiobook)
    with _manifest_lock:
        cached = _cover_cache.get(audiobook_id)
        if cached and cached[0] == signature:
            _cover_cache.move_to_end(audiobook_id)
            return cached[1]

    cover = None
    for track in audiobook["_tracks"][:3]:
        cover = _cover_from_track(track["path"])
        if cover:
            if len(cover[0]) > _MAX_COVER_BYTES:
                cover = None
            break

    with _manifest_lock:
        _cover_cache[audiobook_id] = (signature, cover)
        _cover_cache.move_to_end(audiobook_id)
        while len(_cover_cache) > _MAX_COVER_CACHE_ENTRIES:
            _cover_cache.popitem(last=False)
    return cover


def clear_audiobook_caches() -> None:
    with _manifest_lock:
        _manifest_cache.clear()
        _cover_cache.clear()
        _group_cache.clear()
