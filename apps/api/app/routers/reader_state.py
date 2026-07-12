"""Single-user reader state and annotation synchronization."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..db import (
    PublicationReadingState,
    ReaderAnnotation,
    get_db,
)
from ..rate_limit import limiter
from ..services.media_library import (
    SUPPORTED_DISCUSSION_EXTENSIONS,
    media_id_for_path,
    reader_kind,
)
from ..services.reader_profiles import (
    DEFAULT_READER_PREFERENCES,
    get_or_create_reader_profile,
    reader_profile_id,
)
from ..settings import settings
from .library import resolve_library_path

router = APIRouter(prefix="/reader", tags=["reader"])


class ReaderPreferencesPayload(BaseModel):
    theme: Literal["paper", "night", "contrast"] = "paper"
    flow: Literal["paginated", "scrolled"] = "paginated"
    fontSize: int = Field(18, ge=12, le=32)
    lineHeight: float = Field(1.72, ge=1.2, le=2.5)
    maxWidth: int = Field(680, ge=360, le=1200)


class ReaderLocationPayload(BaseModel):
    fraction: float = Field(0, ge=0, le=1)
    cfi: str | None = Field(None, max_length=4096)
    chapter: str | None = Field(None, max_length=500)
    page: str | None = Field(None, max_length=100)


class ReaderTargetPayload(BaseModel):
    kind: Literal["foliate", "pdf", "text"]
    cfi: str | None = Field(None, max_length=4096)
    page: int | None = Field(None, ge=1, le=1_000_000)
    offset: int | None = Field(None, ge=0)
    fraction: float | None = Field(None, ge=0, le=1)
    length: int | None = Field(None, ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_target(self):
        if self.kind == "foliate" and not self.cfi:
            raise ValueError("Foliate targets require a CFI")
        if self.kind == "pdf" and self.page is None:
            raise ValueError("PDF targets require a page")
        if self.kind == "text" and (
            self.offset is None or self.fraction is None
        ):
            raise ValueError("Text targets require an offset and fraction")
        return self


class ReaderPublicationPayload(BaseModel):
    file_path: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(None, max_length=500)
    extension: str = Field(min_length=1, max_length=20, pattern=r"^[a-zA-Z0-9]+$")
    reader_kind: Literal["foliate", "pdf", "text"]
    can_discuss: bool = False
    book_id: str | None = Field(None, max_length=36)
    ingest_status: str | None = Field(None, max_length=30)


class ReaderStateUpsert(ReaderPublicationPayload):
    location: ReaderLocationPayload
    preferences: ReaderPreferencesPayload | None = None


class ReaderAnnotationUpsert(BaseModel):
    publication: ReaderPublicationPayload
    kind: Literal["highlight", "note", "bookmark"]
    quote: str = Field("", max_length=4000)
    note: str = Field("", max_length=20_000)
    fraction: float = Field(0, ge=0, le=1)
    chapter: str | None = Field(None, max_length=500)
    page: str | None = Field(None, max_length=100)
    target: ReaderTargetPayload | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ReaderAnnotationResponse(BaseModel):
    id: str
    kind: str
    quote: str
    note: str
    fraction: float
    chapter: str | None = None
    page: str | None = None
    target: dict | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class PublicationReadingStateResponse(BaseModel):
    id: str
    publication_id: str
    file_path: str
    title: str
    author: str | None = None
    extension: str
    reader_kind: str
    can_discuss: bool
    book_id: str | None = None
    ingest_status: str | None = None
    fraction: float
    chapter: str | None = None
    page: str | None = None
    location: dict
    updated_at: datetime


class ReaderStateResponse(BaseModel):
    publication_id: str
    preferences: ReaderPreferencesPayload
    preferences_updated_at: datetime
    state: PublicationReadingStateResponse | None = None
    annotations: list[ReaderAnnotationResponse] = Field(default_factory=list)


class RecentReadingResponse(BaseModel):
    books: list[PublicationReadingStateResponse]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _publication_identity(file_path: str) -> tuple[Path, str]:
    resolved = resolve_library_path(settings.books_dir, Path(file_path))
    if not resolved.is_file():
        raise HTTPException(404, "Publication not found")
    root = Path(settings.books_dir or "").resolve()
    return resolved, media_id_for_path(root, resolved)


def _find_state(
    db: Session,
    publication_id: str,
) -> PublicationReadingState | None:
    return (
        db.query(PublicationReadingState)
        .filter(
            PublicationReadingState.profile_id == reader_profile_id(),
            PublicationReadingState.publication_id == publication_id,
        )
        .first()
    )


def _apply_publication(
    state: PublicationReadingState,
    publication: ReaderPublicationPayload,
    resolved_path: Path,
) -> None:
    state.source_path = str(resolved_path)
    state.title = publication.title
    state.author = publication.author
    state.extension = publication.extension.lower()
    state.reader_kind = publication.reader_kind
    state.can_discuss = publication.can_discuss
    state.book_id = publication.book_id
    state.ingest_status = publication.ingest_status


def _ensure_state(
    db: Session,
    publication: ReaderPublicationPayload,
) -> PublicationReadingState:
    resolved_path, publication_id = _publication_identity(publication.file_path)
    state = _find_state(db, publication_id)
    if not state:
        get_or_create_reader_profile(db)
        state = PublicationReadingState(
            profile_id=reader_profile_id(),
            publication_id=publication_id,
            source_path=str(resolved_path),
            title=publication.title,
            author=publication.author,
            extension=publication.extension.lower(),
            reader_kind=publication.reader_kind,
            can_discuss=publication.can_discuss,
            book_id=publication.book_id,
            ingest_status=publication.ingest_status,
            fraction=0,
            location_json={},
        )
        db.add(state)
        db.flush()
    else:
        _apply_publication(state, publication, resolved_path)
    return state


def _annotation_response(annotation: ReaderAnnotation) -> ReaderAnnotationResponse:
    return ReaderAnnotationResponse(
        id=annotation.id,
        kind=annotation.kind,
        quote=annotation.quote,
        note=annotation.note,
        fraction=annotation.fraction,
        chapter=annotation.chapter,
        page=annotation.page,
        target=annotation.target_json,
        created_at=_as_utc(annotation.created_at),
        updated_at=_as_utc(annotation.updated_at),
        deleted_at=_as_utc(annotation.deleted_at),
    )


def _state_response(state: PublicationReadingState) -> PublicationReadingStateResponse:
    return PublicationReadingStateResponse(
        id=state.id,
        publication_id=state.publication_id,
        file_path=state.source_path,
        title=state.title,
        author=state.author,
        extension=state.extension,
        reader_kind=state.reader_kind,
        can_discuss=state.can_discuss,
        book_id=state.book_id,
        ingest_status=state.ingest_status,
        fraction=state.fraction,
        chapter=state.chapter,
        page=state.page,
        location=state.location_json,
        updated_at=_as_utc(state.updated_at),
    )


def _full_response(
    db: Session,
    publication_id: str,
) -> ReaderStateResponse:
    profile = get_or_create_reader_profile(db)
    state = _find_state(db, publication_id)
    annotations = []
    if state:
        annotations = (
            db.query(ReaderAnnotation)
            .filter(ReaderAnnotation.reading_state_id == state.id)
            .order_by(ReaderAnnotation.created_at.desc())
            .all()
        )
    return ReaderStateResponse(
        publication_id=publication_id,
        preferences=ReaderPreferencesPayload.model_validate(
            {**DEFAULT_READER_PREFERENCES, **(profile.preferences_json or {})}
        ),
        preferences_updated_at=_as_utc(profile.updated_at),
        state=_state_response(state) if state else None,
        annotations=[_annotation_response(annotation) for annotation in annotations],
    )


@router.get("/state", response_model=ReaderStateResponse)
@limiter.limit("180/minute")
def get_reader_state(
    request: Request,
    file_path: str = Query(min_length=1, max_length=4096),
    db: Session = Depends(get_db),
):
    _, publication_id = _publication_identity(file_path)
    response = _full_response(db, publication_id)
    db.commit()
    return response


@router.put("/state", response_model=ReaderStateResponse)
@limiter.limit("300/minute")
def save_reader_state(
    request: Request,
    payload: ReaderStateUpsert = Body(...),
    db: Session = Depends(get_db),
):
    state = _ensure_state(db, payload)
    location = payload.location.model_dump(exclude_none=True)
    state.location_json = location
    state.fraction = payload.location.fraction
    state.chapter = payload.location.chapter
    state.page = payload.location.page
    state.updated_at = datetime.utcnow()
    if payload.preferences:
        profile = get_or_create_reader_profile(db)
        profile.preferences_json = payload.preferences.model_dump()
        profile.updated_at = datetime.utcnow()
    db.commit()
    return _full_response(db, state.publication_id)


@router.put(
    "/annotations/{annotation_id}",
    response_model=ReaderAnnotationResponse,
)
@limiter.limit("180/minute")
def save_reader_annotation(
    request: Request,
    annotation_id: UUID,
    payload: ReaderAnnotationUpsert = Body(...),
    db: Session = Depends(get_db),
):
    state = _ensure_state(db, payload.publication)
    annotation_key = str(annotation_id)
    annotation = db.get(ReaderAnnotation, annotation_key)
    incoming_updated_at = _as_naive_utc(payload.updated_at or payload.created_at)

    if annotation and annotation.reading_state_id != state.id:
        raise HTTPException(409, "Annotation ID belongs to another publication")
    if annotation and annotation.deleted_at:
        if incoming_updated_at <= annotation.deleted_at:
            return _annotation_response(annotation)
        annotation.deleted_at = None

    if not annotation:
        active_count = (
            db.query(ReaderAnnotation)
            .filter(
                ReaderAnnotation.reading_state_id == state.id,
                ReaderAnnotation.deleted_at.is_(None),
            )
            .count()
        )
        if active_count >= 500:
            raise HTTPException(400, "This publication already has 500 active marks")
        annotation = ReaderAnnotation(
            id=annotation_key,
            reading_state_id=state.id,
            kind=payload.kind,
            quote=payload.quote,
            note=payload.note,
            fraction=payload.fraction,
            chapter=payload.chapter,
            page=payload.page,
            target_json=(
                payload.target.model_dump(exclude_none=True)
                if payload.target
                else None
            ),
            created_at=_as_naive_utc(payload.created_at),
            updated_at=datetime.utcnow(),
        )
        db.add(annotation)
    else:
        annotation.kind = payload.kind
        annotation.quote = payload.quote
        annotation.note = payload.note
        annotation.fraction = payload.fraction
        annotation.chapter = payload.chapter
        annotation.page = payload.page
        annotation.target_json = (
            payload.target.model_dump(exclude_none=True) if payload.target else None
        )
        annotation.updated_at = datetime.utcnow()

    state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(annotation)
    return _annotation_response(annotation)


@router.delete(
    "/annotations/{annotation_id}",
    response_model=ReaderAnnotationResponse,
)
@limiter.limit("180/minute")
def delete_reader_annotation(
    request: Request,
    annotation_id: UUID,
    file_path: str = Query(min_length=1, max_length=4096),
    db: Session = Depends(get_db),
):
    resolved_path, publication_id = _publication_identity(file_path)
    state = _find_state(db, publication_id)
    if not state:
        extension = resolved_path.suffix.lower().lstrip(".")
        renderer = reader_kind(extension)
        if renderer not in {"foliate", "pdf", "text"}:
            raise HTTPException(400, "Publication does not have a reader")
        state = _ensure_state(
            db,
            ReaderPublicationPayload(
                file_path=str(resolved_path),
                title=resolved_path.stem,
                extension=extension,
                reader_kind=renderer,
                can_discuss=(
                    resolved_path.suffix.lower() in SUPPORTED_DISCUSSION_EXTENSIONS
                ),
            ),
        )

    annotation_key = str(annotation_id)
    annotation = db.get(ReaderAnnotation, annotation_key)
    if annotation and annotation.reading_state_id != state.id:
        raise HTTPException(409, "Annotation ID belongs to another publication")
    now = datetime.utcnow()
    if not annotation:
        annotation = ReaderAnnotation(
            id=annotation_key,
            reading_state_id=state.id,
            kind="note",
            quote="",
            note="",
            fraction=state.fraction,
            created_at=now,
            updated_at=now,
            deleted_at=now,
        )
        db.add(annotation)
    else:
        annotation.deleted_at = now
        annotation.updated_at = now
    state.updated_at = now
    db.commit()
    db.refresh(annotation)
    return _annotation_response(annotation)


@router.get("/recent", response_model=RecentReadingResponse)
@limiter.limit("180/minute")
def recent_reading(
    request: Request,
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
):
    states = (
        db.query(PublicationReadingState)
        .filter(PublicationReadingState.profile_id == reader_profile_id())
        .order_by(PublicationReadingState.updated_at.desc())
        .limit(limit)
        .all()
    )
    return RecentReadingResponse(books=[_state_response(state) for state in states])
