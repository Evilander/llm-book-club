"""Library endpoints for browsing books, exploring text, and pairing local audio."""
from __future__ import annotations

import mimetypes
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..db import Book, BookMemory, Chunk, IngestStatus, ReadingUnit, Section, get_db
from ..rate_limit import limiter
from ..services.reading_progress import choose_section_for_unit
from ..services.reader_text import assemble_reading_text, page_bounds
from ..services.media_library import (
    ROOT_FOLDER_SENTINEL,
    SUPPORTED_AUDIOBOOK_EXTENSIONS,
    SUPPORTED_BOOK_EXTENSIONS,
    clear_scan_cache,
    guess_title,
    match_audiobooks_for_book,
    scan_media_dir,
    summarize_media_folders,
)
from ..settings import settings
from ..worker import enqueue_ingestion_from_path, is_bindery_paused, set_bindery_paused

router = APIRouter(tags=["library"])
BULK_FOLDER_INGEST_LIMIT = 500

_AUDIO_MEDIA_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".m4b": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


class LocalBookEntry(BaseModel):
    path: str
    filename: str
    extension: str
    size_bytes: int
    title_guess: str
    parent_folder: str | None = None
    already_ingested: bool = False
    book_id: str | None = None


class LocalLibraryResponse(BaseModel):
    books_dir: str
    total: int
    books: list[LocalBookEntry]


class LocalFolderEntry(BaseModel):
    name: str
    path: str
    book_count: int
    audiobook_count: int = 0
    sample_titles: list[str]


class LocalFolderLibraryResponse(BaseModel):
    books_dir: str
    total_books: int
    folders: list[LocalFolderEntry]
    root_book_count: int


class LocalAudiobookEntry(BaseModel):
    path: str
    filename: str
    extension: str
    size_bytes: int
    title_guess: str
    parent_folder: str | None = None
    match_score: float | None = None
    match_reason: str | None = None


class LocalAudiobookLibraryResponse(BaseModel):
    audiobooks_dir: str
    total: int
    books: list[LocalAudiobookEntry]


class LocalIngestResponse(BaseModel):
    book_id: str
    filename: str
    size_bytes: int
    status: str


class LocalFolderIngestRequest(BaseModel):
    folder: str
    limit: int | None = None
    include_already_ingested: bool = False


class LocalFolderSkippedOversize(BaseModel):
    path: str
    filename: str
    size_bytes: int


class LocalFolderIngestResponse(BaseModel):
    folder: str
    total_in_folder: int
    already_ingested_count: int
    queued_count: int
    queued_book_ids: list[str]
    skipped_oversize: list[LocalFolderSkippedOversize]


class BinderyStatusResponse(BaseModel):
    paused: bool
    queued: int
    processing: int
    failed_recent: int


class BinderyPauseRequest(BaseModel):
    paused: bool


class LibrarySearchResult(BaseModel):
    source: Literal["ingested", "library"]
    title: str
    author: str | None = None
    book_id: str | None = None
    path: str | None = None
    parent_folder: str | None = None
    extension: str | None = None
    size_bytes: int | None = None
    audiobook_count: int = 0
    score: int


class LibrarySearchResponse(BaseModel):
    query: str
    total: int
    ingested_count: int
    library_count: int
    results: list[LibrarySearchResult]


class ReaderChunkSpan(BaseModel):
    chunk_id: str
    section_id: str
    char_start: int
    char_end: int


class ReaderPageResponse(BaseModel):
    book_id: str
    title: str
    author: str | None
    page: int
    page_size: int
    total_pages: int
    total_chars: int
    current_section_id: str | None
    current_section_title: str | None
    current_section_order: int | None
    text: str
    char_start: int
    char_end: int  # exclusive, in the assembled reading edition
    chunks: list[ReaderChunkSpan] = []


class ExploreSectionSummary(BaseModel):
    id: str
    title: str | None = None
    section_type: str
    order_index: int
    reading_time_min: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    preview_text: str = ""


class ExploreSectionDetail(ExploreSectionSummary):
    text: str
    chunk_count: int
    source_refs: list[str] = []
    chunks: list[ReaderChunkSpan] = []


class BookProgressSummary(BaseModel):
    current_unit_id: str | None = None
    current_unit_title: str | None = None
    resume_section_id: str | None = None
    resume_section_title: str | None = None
    units_completed: int = 0
    total_units: int = 0
    reading_progress_pct: float = 0.0
    last_read_at: str | None = None


class BookExploreResponse(BaseModel):
    book_id: str
    title: str
    author: str | None = None
    filename: str
    file_type: str
    total_chars: int | None = None
    source_path: str | None = None
    sections: list[ExploreSectionSummary]
    active_section: ExploreSectionDetail | None = None
    audiobook_matches: list[LocalAudiobookEntry]
    has_local_audiobook: bool
    audiobooks_dir: str | None = None
    progress: BookProgressSummary | None = None


def _resolve_library_path(root_dir: str | None, file_path: Path) -> Path:
    if not root_dir:
        raise HTTPException(400, "Library directory is not configured")

    try:
        resolved = file_path.resolve()
        allowed_root = Path(root_dir).resolve()
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(400, "Invalid file path")

    if allowed_root not in resolved.parents and resolved != allowed_root:
        raise HTTPException(403, "File path is outside the configured library directory")
    return resolved


def _resolve_direct_library_folder(folder: str) -> Path:
    if not settings.books_dir:
        raise HTTPException(400, "Library directory is not configured")

    folder_name = folder.strip()
    folder_path = Path(folder_name)
    if (
        not folder_name
        or folder_path.is_absolute()
        or len(folder_path.parts) != 1
        or folder_path.parts[0] in {".", "..", ROOT_FOLDER_SENTINEL}
    ):
        raise HTTPException(403, "Folder must be a direct child of BOOKS_DIR")

    root = Path(settings.books_dir).resolve()
    resolved_folder = _resolve_library_path(settings.books_dir, root / folder_name)
    if resolved_folder.parent != root:
        raise HTTPException(403, "Folder must be a direct child of BOOKS_DIR")
    if not resolved_folder.exists() or not resolved_folder.is_dir():
        raise HTTPException(404, "Folder not found")
    return resolved_folder


def _scan_local_books(*, refresh: bool = False) -> list[dict]:
    return scan_media_dir(
        settings.books_dir,
        extensions=SUPPORTED_BOOK_EXTENSIONS,
        refresh=refresh,
    )


def _scan_local_audiobooks(*, refresh: bool = False) -> list[dict]:
    return scan_media_dir(
        settings.audiobooks_dir,
        extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
        refresh=refresh,
    )


def _lookup_ingested_books(
    db: Session,
    entries: list[dict],
) -> dict[str, str]:
    if not entries:
        return {}

    filenames = {entry["filename"] for entry in entries}
    rows = db.query(Book).filter(Book.filename.in_(filenames)).all()

    matched: dict[str, str] = {}
    for entry in entries:
        entry_path = entry["path"]
        for row in rows:
            if row.filename != entry["filename"]:
                continue
            source_path = None
            if isinstance(row.metadata_json, dict):
                source_path = row.metadata_json.get("source_path")
            if source_path and source_path == entry_path:
                matched[entry_path] = str(row.id)
                break
            if row.filename == entry["filename"] and entry_path not in matched:
                matched[entry_path] = str(row.id)

    return matched


def _section_preview_text(chunks: list[Chunk], limit: int = 280) -> str:
    joined = " ".join(chunk.text.strip() for chunk in chunks if chunk.text).strip()
    if len(joined) <= limit:
        return joined
    return f"{joined[:limit].rstrip()}..."


def _serialize_section_detail(section: Section, chunks: list[Chunk]) -> ExploreSectionDetail:
    reading = assemble_reading_text(chunks)
    text = reading.text
    refs = [chunk.source_ref for chunk in chunks if chunk.source_ref]
    return ExploreSectionDetail(
        id=section.id,
        title=section.title,
        section_type=section.section_type,
        order_index=section.order_index,
        reading_time_min=section.reading_time_min,
        page_start=section.page_start,
        page_end=section.page_end,
        preview_text=_section_preview_text(chunks),
        text=text,
        chunk_count=len(chunks),
        source_refs=refs,
        chunks=reading.chunks,
    )


def _build_progress_summary(
    db: Session,
    *,
    book_id: str,
    sections: list[Section],
    memory: BookMemory | None = None,
    units: list[ReadingUnit] | None = None,
) -> BookProgressSummary | None:
    memory = memory or db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        return None

    if units is None:
        units = (
            db.query(ReadingUnit)
            .filter(ReadingUnit.book_id == book_id)
            .order_by(ReadingUnit.order_index)
            .all()
        )

    total_units = len(units)
    completed_count = len(memory.units_completed or [])
    current_unit = next((unit for unit in units if unit.id == memory.current_unit_id), None)
    resume_section = choose_section_for_unit(sections, current_unit)

    return BookProgressSummary(
        current_unit_id=memory.current_unit_id,
        current_unit_title=current_unit.title if current_unit else None,
        resume_section_id=resume_section.id if resume_section else None,
        resume_section_title=resume_section.title if resume_section else None,
        units_completed=completed_count,
        total_units=total_units,
        reading_progress_pct=(completed_count / total_units * 100) if total_units > 0 else 0.0,
        last_read_at=memory.last_read_at.isoformat() if memory.last_read_at else None,
    )


def _field_score(query: str, *, title: str, author: str | None = None, filename: str | None = None, parent_folder: str | None = None) -> int:
    q = query.lower()
    title_lower = title.lower()
    author_lower = (author or "").lower()
    filename_lower = (filename or "").lower()
    parent_lower = (parent_folder or "").lower()
    score = 0

    if title_lower == q:
        score = max(score, 100)
    if title_lower.startswith(q):
        score = max(score, 80)
    if q in title_lower:
        score = max(score, 50)
    if q in author_lower:
        score = max(score, 40)
    if q in filename_lower:
        score = max(score, 30)
    if q in parent_lower:
        score = max(score, 20)

    return score


def _book_parent_folder(book: Book) -> str | None:
    if not isinstance(book.metadata_json, dict):
        return None
    parent = book.metadata_json.get("source_parent")
    if isinstance(parent, str) and parent:
        return parent
    source_path = book.metadata_json.get("source_path")
    if isinstance(source_path, str) and source_path:
        return Path(source_path).parent.name or None
    return None


def _audiobook_count_for_title(
    *,
    title: str,
    author: str | None = None,
    audiobook_entries: list[dict],
) -> int:
    return len(
        match_audiobooks_for_book(
            book_title=title,
            book_author=author,
            audiobook_entries=audiobook_entries,
            limit=max(1, len(audiobook_entries)),
        )
    )


def _build_bindery_status(db: Session) -> BinderyStatusResponse:
    failed_cutoff = datetime.utcnow() - timedelta(hours=24)
    return BinderyStatusResponse(
        paused=is_bindery_paused(),
        queued=db.query(Book).filter(Book.ingest_status == IngestStatus.QUEUED).count(),
        processing=db.query(Book).filter(Book.ingest_status == IngestStatus.PROCESSING).count(),
        failed_recent=(
            db.query(Book)
            .filter(
                Book.ingest_status == IngestStatus.FAILED,
                Book.updated_at >= failed_cutoff,
            )
            .count()
        ),
    )


@router.get("/library/local", response_model=LocalLibraryResponse)
def list_local_books(
    search: str | None = None,
    extension: str | None = None,
    folder: str | None = None,
    skip: int = 0,
    limit: int = 100,
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    if not settings.books_dir:
        raise HTTPException(
            400,
            "BOOKS_DIR not configured. Set the BOOKS_DIR environment variable to your books folder path.",
        )

    if refresh:
        clear_scan_cache()

    all_files = _scan_local_books(refresh=refresh)

    if folder:
        if folder == ROOT_FOLDER_SENTINEL:
            all_files = [item for item in all_files if not item.get("parent_folder")]
        else:
            all_files = [item for item in all_files if item.get("parent_folder") == folder]

    if extension:
        ext = extension.lower().lstrip(".")
        all_files = [item for item in all_files if item["extension"] == ext]

    if search:
        search_lower = search.lower()
        all_files = [
            item
            for item in all_files
            if search_lower in item["filename"].lower()
            or search_lower in item["title_guess"].lower()
            or search_lower in item.get("parent_folder", "").lower()
        ]

    total = len(all_files)
    page = all_files[skip : skip + limit]
    ingested_by_path = _lookup_ingested_books(db, page)

    return LocalLibraryResponse(
        books_dir=settings.books_dir,
        total=total,
        books=[
            LocalBookEntry(
                **entry,
                already_ingested=entry["path"] in ingested_by_path,
                book_id=ingested_by_path.get(entry["path"]),
            )
            for entry in page
        ],
    )


@router.get("/library/local/folders", response_model=LocalFolderLibraryResponse)
def list_local_folders(refresh: bool = False):
    if not settings.books_dir:
        raise HTTPException(
            400,
            "BOOKS_DIR not configured. Set the BOOKS_DIR environment variable to your books folder path.",
        )

    if refresh:
        clear_scan_cache()

    book_entries = _scan_local_books(refresh=refresh)
    audiobook_entries = _scan_local_audiobooks(refresh=refresh) if settings.audiobooks_dir else []
    return LocalFolderLibraryResponse(
        **summarize_media_folders(
            books_dir=settings.books_dir,
            book_entries=book_entries,
            audiobook_entries=audiobook_entries,
        )
    )


@router.get("/library/search", response_model=LibrarySearchResponse)
def library_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = q.strip()
    if not query:
        raise HTTPException(422, "q must not be blank")

    like = f"%{query}%"
    ingested_books = (
        db.query(Book)
        .filter(
            Book.title.ilike(like)
            | Book.author.ilike(like)
            | Book.filename.ilike(like)
        )
        .all()
    )

    ingested_results: list[LibrarySearchResult] = []
    for book in ingested_books:
        score = _field_score(
            query,
            title=book.title,
            author=book.author,
            filename=book.filename,
            parent_folder=_book_parent_folder(book),
        )
        if score <= 0:
            continue
        ingested_results.append(
            LibrarySearchResult(
                source="ingested",
                title=book.title,
                author=book.author,
                book_id=str(book.id),
                parent_folder=_book_parent_folder(book),
                extension=book.file_type,
                size_bytes=book.file_size_bytes,
                score=score,
            )
        )

    library_results: list[LibrarySearchResult] = []
    for entry in _scan_local_books(refresh=False):
        title = entry.get("title_guess") or guess_title(entry["filename"])
        score = _field_score(
            query,
            title=title,
            filename=entry.get("filename"),
            parent_folder=entry.get("parent_folder"),
        )
        if score <= 0:
            continue
        library_results.append(
            LibrarySearchResult(
                source="library",
                title=title,
                path=entry.get("path"),
                parent_folder=entry.get("parent_folder"),
                extension=entry.get("extension"),
                size_bytes=entry.get("size_bytes"),
                score=score,
            )
        )

    combined = sorted(
        [*ingested_results, *library_results],
        key=lambda item: (-item.score, item.title.lower()),
    )
    page = combined[offset : offset + limit]
    audiobook_entries = _scan_local_audiobooks(refresh=False)
    for item in page:
        item.audiobook_count = _audiobook_count_for_title(
            title=item.title,
            author=item.author,
            audiobook_entries=audiobook_entries,
        )

    return LibrarySearchResponse(
        query=query,
        total=len(combined),
        ingested_count=len(ingested_results),
        library_count=len(library_results),
        results=page,
    )


@router.get("/library/local/audiobooks", response_model=LocalAudiobookLibraryResponse)
def list_local_audiobooks(
    search: str | None = None,
    extension: str | None = None,
    skip: int = 0,
    limit: int = 100,
    refresh: bool = False,
):
    if not settings.audiobooks_dir:
        raise HTTPException(
            400,
            "AUDIOBOOKS_DIR not configured. Set the AUDIOBOOKS_DIR environment variable to your audiobook folder path.",
        )

    if refresh:
        clear_scan_cache()

    all_files = _scan_local_audiobooks(refresh=refresh)

    if extension:
        ext = extension.lower().lstrip(".")
        all_files = [item for item in all_files if item["extension"] == ext]

    if search:
        search_lower = search.lower()
        all_files = [
            item
            for item in all_files
            if search_lower in item["filename"].lower()
            or search_lower in item["title_guess"].lower()
            or search_lower in item.get("parent_folder", "").lower()
        ]

    total = len(all_files)
    page = all_files[skip : skip + limit]

    return LocalAudiobookLibraryResponse(
        audiobooks_dir=settings.audiobooks_dir,
        total=total,
        books=[LocalAudiobookEntry(**entry) for entry in page],
    )


@router.get("/library/local/audiobooks/stream")
@limiter.limit("30/minute")
async def stream_local_audiobook(
    request: Request,
    path: str = Query(..., min_length=1),
):
    """Stream a matched local audiobook file through the API.

    The browser cannot safely read arbitrary local file paths, so the frontend
    passes the matched path back and this endpoint re-validates it against the
    configured audiobook root before serving bytes.
    """
    if not settings.audiobooks_dir:
        raise HTTPException(
            400,
            "AUDIOBOOKS_DIR not configured. Set the AUDIOBOOKS_DIR environment variable to your audiobook folder path.",
        )

    resolved_path = _resolve_library_path(settings.audiobooks_dir, Path(path))
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(404, "Audiobook file not found")

    ext = resolved_path.suffix.lower()
    if ext not in SUPPORTED_AUDIOBOOK_EXTENSIONS:
        raise HTTPException(400, f"Unsupported audiobook type: {ext}")

    media_type = _AUDIO_MEDIA_TYPES.get(ext) or mimetypes.guess_type(resolved_path.name)[0]
    return FileResponse(
        resolved_path,
        media_type=media_type or "application/octet-stream",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/library/bindery/status", response_model=BinderyStatusResponse)
def bindery_status(db: Session = Depends(get_db)):
    return _build_bindery_status(db)


@router.post("/library/bindery/pause", response_model=BinderyStatusResponse)
@limiter.limit("6/minute")
async def set_bindery_pause(
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    try:
        payload = BinderyPauseRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc

    set_bindery_paused(payload.paused)
    return _build_bindery_status(db)


@router.post("/books/{book_id}/retry", response_model=LocalIngestResponse)
@limiter.limit("3/minute")
async def retry_book(
    request: Request,
    book_id: str,
    db: Session = Depends(get_db),
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")
    if book.ingest_status != IngestStatus.FAILED:
        raise HTTPException(422, "Only failed books can be retried")

    metadata = dict(book.metadata_json or {})
    source_path = metadata.get("source_path")
    if not isinstance(source_path, str) or not source_path.strip():
        raise HTTPException(422, "metadata_json.source_path is required to retry this book")

    metadata.pop("stage", None)
    metadata.pop("stage_started_at", None)
    book.ingest_status = IngestStatus.QUEUED
    book.ingest_error = None
    book.metadata_json = metadata
    db.add(book)
    db.commit()
    db.refresh(book)

    enqueue_ingestion_from_path(book.id, source_path, book.filename)

    return LocalIngestResponse(
        book_id=str(book.id),
        filename=book.filename,
        size_bytes=book.file_size_bytes,
        status=book.ingest_status.value,
    )


@router.post("/library/local/ingest_folder", response_model=LocalFolderIngestResponse)
@limiter.limit("1/minute")
async def ingest_local_folder(
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    try:
        payload = LocalFolderIngestRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc

    resolved_folder = _resolve_direct_library_folder(payload.folder)
    folder_name = resolved_folder.name

    if payload.limit is not None:
        if payload.limit < 1:
            raise HTTPException(400, "limit must be at least 1")
        if payload.limit > BULK_FOLDER_INGEST_LIMIT:
            raise HTTPException(
                400,
                "Bulk folder ingest is capped at 500 books per request; use multiple requests for larger folders.",
            )

    folder_entries = [
        entry
        for entry in _scan_local_books(refresh=False)
        if entry.get("parent_folder") == folder_name
    ]
    total_in_folder = len(folder_entries)

    ingested_by_path = _lookup_ingested_books(db, folder_entries)
    already_ingested_count = len(ingested_by_path)
    candidates = (
        folder_entries
        if payload.include_already_ingested
        else [entry for entry in folder_entries if entry["path"] not in ingested_by_path]
    )

    requested_count = len(candidates) if payload.limit is None else min(payload.limit, len(candidates))
    if requested_count > BULK_FOLDER_INGEST_LIMIT:
        raise HTTPException(
            400,
            "Bulk folder ingest is capped at 500 books per request; use multiple requests for larger folders.",
        )

    local_limit_mb = settings.local_ingest_max_mb
    max_bytes = local_limit_mb * 1024 * 1024 if local_limit_mb > 0 else None
    skipped_oversize: list[LocalFolderSkippedOversize] = []
    queued_books: list[tuple[Book, Path, str]] = []

    for entry in candidates[:requested_count]:
        resolved_path = _resolve_library_path(settings.books_dir, Path(entry["path"]))
        if resolved_folder not in resolved_path.parents:
            raise HTTPException(403, "File path is outside the requested library folder")
        if not resolved_path.exists() or not resolved_path.is_file():
            continue

        size_bytes = int(entry["size_bytes"])
        if max_bytes is not None and size_bytes > max_bytes:
            skipped_oversize.append(
                LocalFolderSkippedOversize(
                    path=str(resolved_path),
                    filename=entry["filename"],
                    size_bytes=size_bytes,
                )
            )
            continue

        ext = resolved_path.suffix.lower()
        if ext not in SUPPORTED_BOOK_EXTENSIONS:
            continue

        book = Book(
            title=entry.get("title_guess") or guess_title(entry["filename"]),
            filename=entry["filename"],
            file_type=ext.lstrip("."),
            file_size_bytes=size_bytes,
            ingest_status=IngestStatus.QUEUED,
            metadata_json={
                "ingest_source": "local_library",
                "source_path": str(resolved_path),
                "source_parent": folder_name,
            },
        )
        db.add(book)
        queued_books.append((book, resolved_path, entry["filename"]))

    db.commit()

    queued_book_ids: list[str] = []
    for book, resolved_path, filename in queued_books:
        db.refresh(book)
        queued_book_ids.append(str(book.id))
        enqueue_ingestion_from_path(book.id, str(resolved_path), filename)

    return LocalFolderIngestResponse(
        folder=folder_name,
        total_in_folder=total_in_folder,
        already_ingested_count=already_ingested_count,
        queued_count=len(queued_book_ids),
        queued_book_ids=queued_book_ids,
        skipped_oversize=skipped_oversize,
    )


@router.post("/library/local/ingest", response_model=LocalIngestResponse)
@limiter.limit("3/minute")
async def ingest_local_book(
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    file_path = body.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        raise HTTPException(422, "file_path is required")

    resolved_path = _resolve_library_path(settings.books_dir, Path(file_path))

    if not resolved_path.exists():
        raise HTTPException(404, "File not found")

    ext = resolved_path.suffix.lower()
    if ext not in SUPPORTED_BOOK_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    size_bytes = resolved_path.stat().st_size
    local_limit_mb = settings.local_ingest_max_mb
    if local_limit_mb > 0 and size_bytes > local_limit_mb * 1024 * 1024:
        raise HTTPException(
            400,
            f"File too large ({size_bytes / 1024 / 1024:.1f}MB). Max: {local_limit_mb}MB",
        )

    filename = resolved_path.name
    existing = db.query(Book).filter(Book.filename == filename).all()
    for row in existing:
        source_path = None
        if isinstance(row.metadata_json, dict):
            source_path = row.metadata_json.get("source_path")
        if source_path == str(resolved_path) or row.filename == filename:
            return LocalIngestResponse(
                book_id=str(row.id),
                filename=filename,
                size_bytes=size_bytes,
                status=row.ingest_status.value,
            )

    book = Book(
        title=guess_title(filename),
        filename=filename,
        file_type=ext.lstrip("."),
        file_size_bytes=size_bytes,
        ingest_status=IngestStatus.QUEUED,
        metadata_json={
            "ingest_source": "local_library",
            "source_path": str(resolved_path),
            "source_parent": resolved_path.parent.name,
        },
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    enqueue_ingestion_from_path(book.id, str(resolved_path), filename)

    return LocalIngestResponse(
        book_id=str(book.id),
        filename=filename,
        size_bytes=size_bytes,
        status="queued",
    )


@router.get("/books/{book_id}/reader", response_model=ReaderPageResponse)
def read_book(
    book_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(1800, ge=200, le=8000),
    db: Session = Depends(get_db),
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    sections = (
        db.query(Section)
        .filter(Section.book_id == book_id)
        .order_by(Section.order_index)
        .all()
    )
    chunks = (
        db.query(Chunk)
        .join(Section, Chunk.section_id == Section.id)
        .filter(Chunk.book_id == book_id)
        .order_by(Section.order_index, Chunk.order_index, Chunk.char_start)
        .all()
    )
    if not chunks:
        raise HTTPException(404, "No readable text found for this book")

    reading = assemble_reading_text(chunks)
    full_text = reading.text
    total_chars = len(full_text)
    if total_chars == 0:
        raise HTTPException(404, "No readable text found for this book")

    total_pages = ceil(total_chars / page_size)
    if page > total_pages:
        raise HTTPException(404, "Reader page is out of range")

    start, end = page_bounds(full_text, page, page_size)
    text = full_text[start:end]
    middle_char = start + max(0, len(text) // 2)
    page_chunks = [span for span in reading.chunks if span["char_start"] < end and span["char_end"] > start]
    middle_chunk = next((span for span in page_chunks if span["char_start"] <= middle_char < span["char_end"]), None)
    current_section = next((section for section in sections if middle_chunk and str(section.id) == middle_chunk["section_id"]), None)

    return ReaderPageResponse(
        book_id=str(book.id),
        title=book.title,
        author=book.author,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_chars=total_chars,
        current_section_id=str(current_section.id) if current_section else None,
        current_section_title=current_section.title if current_section else None,
        current_section_order=current_section.order_index if current_section else None,
        text=text,
        char_start=start,
        char_end=end,
        chunks=page_chunks,
    )


@router.get("/books/{book_id}/explore", response_model=BookExploreResponse)
def explore_book(
    book_id: str,
    section_id: str | None = None,
    db: Session = Depends(get_db),
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    sections = (
        db.query(Section)
        .filter(Section.book_id == book_id)
        .order_by(Section.order_index)
        .all()
    )
    if not sections:
        raise HTTPException(404, "No sections found for this book")

    chunks = (
        db.query(Chunk)
        .filter(Chunk.book_id == book_id)
        .order_by(Chunk.char_start)
        .all()
    )
    chunks_by_section: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        chunks_by_section.setdefault(chunk.section_id, []).append(chunk)

    active_section = next((item for item in sections if item.id == section_id), sections[0])

    source_path = None
    if isinstance(book.metadata_json, dict):
        source_path = book.metadata_json.get("source_path")

    audiobook_matches = [
        LocalAudiobookEntry(**entry)
        for entry in match_audiobooks_for_book(
            book_title=book.title,
            book_author=book.author,
            audiobook_entries=_scan_local_audiobooks(),
        )
    ]

    return BookExploreResponse(
        book_id=str(book.id),
        title=book.title,
        author=book.author,
        filename=book.filename,
        file_type=book.file_type,
        total_chars=book.total_chars,
        source_path=source_path,
        sections=[
            ExploreSectionSummary(
                id=section.id,
                title=section.title,
                section_type=section.section_type,
                order_index=section.order_index,
                reading_time_min=section.reading_time_min,
                page_start=section.page_start,
                page_end=section.page_end,
                preview_text=_section_preview_text(chunks_by_section.get(section.id, [])),
            )
            for section in sections
        ],
        active_section=_serialize_section_detail(
            active_section,
            chunks_by_section.get(active_section.id, []),
        ),
        audiobook_matches=audiobook_matches,
        has_local_audiobook=bool(audiobook_matches),
        audiobooks_dir=settings.audiobooks_dir,
        progress=_build_progress_summary(db, book_id=book_id, sections=sections),
    )


@router.get("/books/{book_id}/reader-location")
def reader_location(
    book_id: str,
    chunk_id: str,
    char_start: int = Query(0, ge=0),
    page_size: int = Query(1800, ge=200, le=8000),
    db: Session = Depends(get_db),
):
    chunks = db.query(Chunk).join(Section, Chunk.section_id == Section.id).filter(Chunk.book_id == book_id).order_by(Section.order_index, Chunk.order_index, Chunk.char_start).all()
    chunk = next((chunk for chunk in chunks if str(chunk.id) == chunk_id), None)
    if not chunk or char_start >= len(chunk.text):
        raise HTTPException(404, "Passage not found in this book")
    reading = assemble_reading_text(chunks)
    span = next(span for span in reading.chunks if span["chunk_id"] == chunk_id)
    position = span["char_start"] + char_start
    page = min(ceil(len(reading.text) / page_size), position // page_size + 1)
    while page_bounds(reading.text, page, page_size)[1] <= position:
        page += 1
    return {"page": page, "section_id": str(chunk.section_id), "char_start": position}
