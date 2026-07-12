"""Local audiobook discovery, playback, and synced listening progress."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import AudiobookListeningState, get_db
from ..rate_limit import limiter
from ..services.audiobooks import (
    audiobook_summary,
    build_audiobook_manifest,
    extract_audiobook_cover,
    find_audiobook,
    find_manifest_track,
    grouped_audiobook_catalog,
    match_audiobook_groups,
    search_audiobooks,
)
from ..services.media_library import (
    CATALOG_VERSION,
    SUPPORTED_AUDIOBOOK_EXTENSIONS,
)
from ..services.catalog_index import get_or_seed_catalog
from ..services.reader_profiles import (
    get_or_create_reader_profile,
    reader_profile_id,
)
from ..settings import settings
from .library import resolve_library_path

router = APIRouter(prefix="/audiobooks", tags=["audiobooks"])

_AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4b": "audio/mp4",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


class AudiobookSummaryResponse(BaseModel):
    id: str
    title: str
    source_kind: str
    extension: str
    extensions: list[str]
    size_bytes: int
    track_count: int
    parent_folder: str | None = None
    modified_at: str | None = None
    match_score: float | None = None
    match_reason: str | None = None


class AudiobookLibraryResponse(BaseModel):
    audiobooks_dir: str
    inherited_from_books: bool
    total: int
    total_tracks: int
    audiobooks: list[AudiobookSummaryResponse]


class AudiobookTrackResponse(BaseModel):
    id: str
    index: int
    title: str
    album: str | None = None
    artist: str | None = None
    filename: str
    extension: str
    size_bytes: int
    duration_seconds: float | None = None
    stream_url: str


class AudiobookManifestResponse(AudiobookSummaryResponse):
    author: str | None = None
    duration_seconds: float | None = None
    tracks: list[AudiobookTrackResponse]


class ListeningStatePayload(BaseModel):
    current_track_id: str = Field(min_length=1, max_length=64)
    position_seconds: float = Field(0, ge=0, le=10_000_000)
    duration_seconds: float | None = Field(None, ge=0, le=10_000_000)
    playback_rate: float = Field(1, ge=0.5, le=3)
    completed: bool = False


class ListeningStateResponse(BaseModel):
    audiobook_id: str
    title: str
    current_track_id: str
    track_index: int
    track_count: int
    position_seconds: float
    duration_seconds: float | None = None
    playback_rate: float
    completed: bool
    persisted: bool
    updated_at: datetime | None = None


class RecentAudiobookResponse(BaseModel):
    books: list[ListeningStateResponse]


def _audio_root() -> tuple[str, bool]:
    root = settings.audiobooks_dir or settings.books_dir
    if not root:
        raise HTTPException(
            400,
            "Neither AUDIOBOOKS_DIR nor BOOKS_DIR is configured",
        )
    resolved = Path(root).resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(404, "Audiobook directory not found")
    return str(resolved), not bool(settings.audiobooks_dir)


def _catalog_cache_file() -> Path | None:
    if settings.app_env == "test":
        return None
    return Path(settings.storage_dir) / "catalog" / f"audiobooks-v{CATALOG_VERSION}.json"


def _audiobook_catalog(db: Session) -> tuple[str, bool, dict, list[dict]]:
    root, inherited = _audio_root()
    catalog = get_or_seed_catalog(
        db,
        root_dir=root,
        kind="audiobooks",
        extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
        index_enabled=settings.media_catalog_index_enabled,
        cache_file=_catalog_cache_file(),
        ttl_seconds=settings.library_catalog_ttl,
    )
    return root, inherited, catalog, grouped_audiobook_catalog(catalog)


def _require_audiobook(db: Session, audiobook_id: str) -> tuple[str, dict]:
    root, _, _, audiobooks = _audiobook_catalog(db)
    audiobook = find_audiobook(audiobooks, audiobook_id)
    if not audiobook:
        raise HTTPException(404, "Audiobook not found")
    return root, audiobook


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_state(
    state: AudiobookListeningState,
    *,
    persisted: bool = True,
) -> ListeningStateResponse:
    return ListeningStateResponse(
        audiobook_id=state.audiobook_id,
        title=state.title,
        current_track_id=state.current_track_id,
        track_index=state.track_index,
        track_count=state.track_count,
        position_seconds=state.position_seconds,
        duration_seconds=state.duration_seconds,
        playback_rate=state.playback_rate,
        completed=state.completed,
        persisted=persisted,
        updated_at=_as_utc(state.updated_at),
    )


def _find_state(db: Session, audiobook_id: str) -> AudiobookListeningState | None:
    return (
        db.query(AudiobookListeningState)
        .filter(
            AudiobookListeningState.profile_id == reader_profile_id(),
            AudiobookListeningState.audiobook_id == audiobook_id,
        )
        .first()
    )


@router.get("", response_model=AudiobookLibraryResponse)
@limiter.limit("120/minute")
def list_audiobooks(
    request: Request,
    search: str | None = Query(None, max_length=500),
    skip: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
):
    root, inherited, catalog, audiobooks = _audiobook_catalog(db)
    matches = search_audiobooks(audiobooks, search)
    return AudiobookLibraryResponse(
        audiobooks_dir=root,
        inherited_from_books=inherited,
        total=len(matches),
        total_tracks=len(catalog["items"]),
        audiobooks=[
            AudiobookSummaryResponse.model_validate(audiobook_summary(item))
            for item in matches[skip : skip + limit]
        ],
    )


@router.get("/matches", response_model=list[AudiobookSummaryResponse])
@limiter.limit("120/minute")
def match_audiobooks(
    request: Request,
    title: str = Query(min_length=1, max_length=500),
    author: str | None = Query(None, max_length=500),
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
):
    _, _, _, audiobooks = _audiobook_catalog(db)
    return [
        AudiobookSummaryResponse.model_validate(item)
        for item in match_audiobook_groups(
            book_title=title,
            book_author=author,
            audiobooks=audiobooks,
            limit=limit,
        )
    ]


@router.get("/recent", response_model=RecentAudiobookResponse)
@limiter.limit("120/minute")
def recent_audiobooks(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    states = (
        db.query(AudiobookListeningState)
        .filter(AudiobookListeningState.profile_id == reader_profile_id())
        .order_by(AudiobookListeningState.updated_at.desc())
        .limit(limit)
        .all()
    )
    return RecentAudiobookResponse(books=[_serialize_state(state) for state in states])


@router.get("/{audiobook_id}", response_model=AudiobookManifestResponse)
@limiter.limit("120/minute")
def audiobook_manifest(
    request: Request,
    audiobook_id: str,
    db: Session = Depends(get_db),
):
    _, audiobook = _require_audiobook(db, audiobook_id)
    manifest = build_audiobook_manifest(audiobook)
    return AudiobookManifestResponse.model_validate(
        {
            **manifest,
            "tracks": [
                {
                    **track,
                    "stream_url": (
                        f"/v1/audiobooks/{audiobook_id}/tracks/{track['id']}/stream"
                    ),
                }
                for track in manifest["tracks"]
            ],
        }
    )


@router.api_route("/{audiobook_id}/cover", methods=["GET", "HEAD"])
@limiter.limit("180/minute")
def audiobook_cover(
    request: Request,
    audiobook_id: str,
    db: Session = Depends(get_db),
):
    _, audiobook = _require_audiobook(db, audiobook_id)
    cover = extract_audiobook_cover(audiobook)
    if not cover:
        raise HTTPException(404, "Audiobook cover not found")
    cover_bytes, media_type = cover
    return Response(
        content=b"" if request.method == "HEAD" else cover_bytes,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Length": str(len(cover_bytes)),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.api_route(
    "/{audiobook_id}/tracks/{track_id}/stream",
    methods=["GET", "HEAD"],
)
@limiter.limit("300/minute")
def stream_audiobook_track(
    request: Request,
    audiobook_id: str,
    track_id: str,
    db: Session = Depends(get_db),
):
    root, audiobook = _require_audiobook(db, audiobook_id)
    track = find_manifest_track(audiobook, track_id)
    if not track:
        raise HTTPException(404, "Audiobook track not found")
    path = resolve_library_path(root, Path(track["path"]))
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_AUDIOBOOK_EXTENSIONS:
        raise HTTPException(404, "Audiobook track not found")
    return FileResponse(
        path=path,
        media_type=_AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        filename=path.name,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{audiobook_id}/state", response_model=ListeningStateResponse)
@limiter.limit("180/minute")
def get_listening_state(
    request: Request,
    audiobook_id: str,
    db: Session = Depends(get_db),
):
    _, audiobook = _require_audiobook(db, audiobook_id)
    state = _find_state(db, audiobook_id)
    if state:
        return _serialize_state(state)
    get_or_create_reader_profile(db)
    db.commit()
    first_track = audiobook["_tracks"][0]
    return ListeningStateResponse(
        audiobook_id=audiobook_id,
        title=audiobook["title"],
        current_track_id=first_track["id"],
        track_index=0,
        track_count=len(audiobook["_tracks"]),
        position_seconds=0,
        playback_rate=1,
        completed=False,
        persisted=False,
    )


@router.put("/{audiobook_id}/state", response_model=ListeningStateResponse)
@limiter.limit("300/minute")
def save_listening_state(
    request: Request,
    audiobook_id: str,
    payload: ListeningStatePayload = Body(...),
    db: Session = Depends(get_db),
):
    _, audiobook = _require_audiobook(db, audiobook_id)
    manifest = build_audiobook_manifest(audiobook)
    track = next(
        (item for item in manifest["tracks"] if item["id"] == payload.current_track_id),
        None,
    )
    if not track:
        raise HTTPException(400, "Track does not belong to this audiobook")

    canonical_duration = track["duration_seconds"] or payload.duration_seconds
    position = payload.position_seconds
    if canonical_duration is not None:
        position = min(position, canonical_duration)
    track_index = int(track["index"])
    state = _find_state(db, audiobook_id)
    if not state:
        profile = get_or_create_reader_profile(db)
        state = AudiobookListeningState(
            profile_id=profile.id,
            audiobook_id=audiobook_id,
            title=manifest["title"],
            source_path=audiobook["source_path"],
            track_count=len(manifest["tracks"]),
            current_track_id=track["id"],
        )
        db.add(state)

    state.title = manifest["title"]
    state.source_path = audiobook["source_path"]
    state.track_count = len(manifest["tracks"])
    state.current_track_id = track["id"]
    state.track_index = track_index
    state.position_seconds = position
    state.duration_seconds = canonical_duration
    state.playback_rate = payload.playback_rate
    state.completed = payload.completed and track_index == len(manifest["tracks"]) - 1
    state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    return _serialize_state(state)
