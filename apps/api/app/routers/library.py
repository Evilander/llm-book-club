"""Library endpoints for browsing books, exploring text, and pairing local audio."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import Book, Chunk, IngestStatus, Section, get_db
from ..rate_limit import limiter
from ..services.media_library import (
    SUPPORTED_AUDIOBOOK_EXTENSIONS,
    SUPPORTED_BOOK_EXTENSIONS,
    guess_title,
    match_audiobooks_for_book,
    scan_media_dir,
)
from ..settings import settings
from ..worker import enqueue_ingestion

router = APIRouter(tags=["library"])


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


class LocalIngestRequest(BaseModel):
    file_path: str


class LocalIngestResponse(BaseModel):
    book_id: str
    filename: str
    size_bytes: int
    status: str


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


def _scan_local_books() -> list[dict]:
    return scan_media_dir(
        settings.books_dir,
        extensions=SUPPORTED_BOOK_EXTENSIONS,
    )


def _scan_local_audiobooks() -> list[dict]:
    return scan_media_dir(
        settings.audiobooks_dir,
        extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
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
    text = "\n\n".join(chunk.text.strip() for chunk in chunks if chunk.text).strip()
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
    )


@router.get("/library/local", response_model=LocalLibraryResponse)
def list_local_books(
    search: str | None = None,
    extension: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if not settings.books_dir:
        raise HTTPException(
            400,
            "BOOKS_DIR not configured. Set the BOOKS_DIR environment variable to your books folder path.",
        )

    all_files = _scan_local_books()

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


@router.get("/library/local/audiobooks", response_model=LocalAudiobookLibraryResponse)
def list_local_audiobooks(
    search: str | None = None,
    extension: str | None = None,
    skip: int = 0,
    limit: int = 100,
):
    if not settings.audiobooks_dir:
        raise HTTPException(
            400,
            "AUDIOBOOKS_DIR not configured. Set the AUDIOBOOKS_DIR environment variable to your audiobook folder path.",
        )

    all_files = _scan_local_audiobooks()

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


@router.post("/library/local/ingest", response_model=LocalIngestResponse)
@limiter.limit("3/minute")
async def ingest_local_book(
    request: Request,
    body: LocalIngestRequest,
    db: Session = Depends(get_db),
):
    resolved_path = _resolve_library_path(settings.books_dir, Path(body.file_path))

    if not resolved_path.exists():
        raise HTTPException(404, "File not found")

    ext = resolved_path.suffix.lower()
    if ext not in SUPPORTED_BOOK_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    size_bytes = resolved_path.stat().st_size
    size_limit = settings.max_upload_mb * 1024 * 1024
    if size_bytes > size_limit:
        raise HTTPException(
            400,
            f"File too large ({size_bytes / 1024 / 1024:.1f}MB). Max: {settings.max_upload_mb}MB",
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

    data = resolved_path.read_bytes()
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

    enqueue_ingestion(book.id, data, filename)

    return LocalIngestResponse(
        book_id=str(book.id),
        filename=filename,
        size_bytes=size_bytes,
        status="queued",
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
    )
