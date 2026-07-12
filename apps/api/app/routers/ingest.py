"""Book ingestion endpoints."""
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..settings import settings
from ..db import get_db, Book, IngestStatus, Section, DiscussionSession
from ..worker import enqueue_ingestion
from ..rate_limit import limiter
from ..services.media_library import SUPPORTED_DISCUSSION_EXTENSIONS
from ..services.catalog_index import get_or_seed_catalog

router = APIRouter(tags=["ingest"])


class IngestResponse(BaseModel):
    book_id: str
    filename: str
    bytes: int
    status: str
    job_id: str | None = None


class BookResponse(BaseModel):
    id: str
    title: str
    author: str | None
    filename: str
    file_type: str
    file_size_bytes: int
    total_chars: int | None
    ingest_status: str
    ingest_error: str | None
    created_at: str
    section_count: int = 0
    session_count: int = 0
    last_session_at: str | None = None
    has_audiobook: bool = False

    model_config = {"from_attributes": True}


class BookListResponse(BaseModel):
    books: list[BookResponse]
    total: int


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("3/minute")
async def ingest_book(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Queue a supported publication for extraction and embedding."""
    filename = file.filename or "unknown"
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_DISCUSSION_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_DISCUSSION_EXTENSIONS))
        raise HTTPException(400, f"Supported file types: {supported}")

    # Stream-read with a running byte cap so a malicious upload cannot exhaust
    # memory before we reject it.
    size_limit = settings.max_upload_mb * 1024 * 1024
    file_chunks: list[bytes] = []
    total_bytes = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > size_limit:
            raise HTTPException(
                400,
                f"File too large. Max size: {settings.max_upload_mb}MB",
            )
        file_chunks.append(chunk)
    file_data = b"".join(file_chunks)

    file_type = extension.lstrip(".")

    book = Book(
        title=filename.rsplit(".", 1)[0],
        filename=filename,
        file_type=file_type,
        file_size_bytes=len(file_data),
        ingest_status=IngestStatus.QUEUED,
        metadata_json={"ingest_source": "upload"},
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    job_id = enqueue_ingestion(book.id, file_data, filename)

    return IngestResponse(
        book_id=book.id,
        filename=filename,
        bytes=len(file_data),
        status="queued",
        job_id=job_id,
    )


@router.get("/books", response_model=BookListResponse)
def list_books(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List all books in the library with enriched metadata for browse."""
    query = db.query(Book).order_by(Book.created_at.desc())
    total = query.count()
    books = query.offset(skip).limit(limit).all()

    book_ids = [b.id for b in books]

    # Batch-fetch section counts
    section_counts: dict[str, int] = {}
    if book_ids:
        rows = (
            db.query(Section.book_id, func.count(Section.id))
            .filter(Section.book_id.in_(book_ids))
            .group_by(Section.book_id)
            .all()
        )
        section_counts = {bid: cnt for bid, cnt in rows}

    # Batch-fetch session counts and last session dates
    session_counts: dict[str, int] = {}
    last_session_dates: dict[str, str] = {}
    if book_ids:
        rows = (
            db.query(
                DiscussionSession.book_id,
                func.count(DiscussionSession.id),
                func.max(DiscussionSession.created_at),
            )
            .filter(DiscussionSession.book_id.in_(book_ids))
            .group_by(DiscussionSession.book_id)
            .all()
        )
        for bid, cnt, last_dt in rows:
            session_counts[bid] = cnt
            if last_dt:
                last_session_dates[bid] = last_dt.isoformat()

    # Check audiobook availability
    has_audiobook: dict[str, bool] = {}
    audiobook_root = settings.audiobooks_dir or settings.books_dir
    if audiobook_root:
        try:
            from ..services.media_library import (
                CATALOG_VERSION,
                SUPPORTED_AUDIOBOOK_EXTENSIONS,
            )
            from ..services.audiobooks import (
                grouped_audiobook_catalog,
                match_audiobook_groups,
            )
            cache_file = (
                None
                if settings.app_env == "test"
                else Path(settings.storage_dir)
                / "catalog"
                / f"audiobooks-v{CATALOG_VERSION}.json"
            )
            audiobook_catalog = get_or_seed_catalog(
                db,
                root_dir=audiobook_root,
                kind="audiobooks",
                extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
                index_enabled=settings.media_catalog_index_enabled,
                cache_file=cache_file,
                ttl_seconds=settings.library_catalog_ttl,
            )
            audiobook_groups = grouped_audiobook_catalog(audiobook_catalog)
            for b in books:
                if b.ingest_status == IngestStatus.COMPLETED:
                    matches = match_audiobook_groups(
                        book_title=b.title,
                        book_author=b.author,
                        audiobooks=audiobook_groups,
                    )
                    has_audiobook[b.id] = len(matches) > 0
        except Exception:
            pass  # Graceful degradation if audiobook matching fails

    return BookListResponse(
        books=[
            BookResponse(
                id=b.id,
                title=b.title,
                author=b.author,
                filename=b.filename,
                file_type=b.file_type,
                file_size_bytes=b.file_size_bytes,
                total_chars=b.total_chars,
                ingest_status=b.ingest_status.value,
                ingest_error=b.ingest_error,
                created_at=b.created_at.isoformat(),
                section_count=section_counts.get(b.id, 0),
                session_count=session_counts.get(b.id, 0),
                last_session_at=last_session_dates.get(b.id),
                has_audiobook=has_audiobook.get(b.id, False),
            )
            for b in books
        ],
        total=total,
    )


@router.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Get a specific book by ID."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    return BookResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        filename=book.filename,
        file_type=book.file_type,
        file_size_bytes=book.file_size_bytes,
        total_chars=book.total_chars,
        ingest_status=book.ingest_status.value,
        ingest_error=book.ingest_error,
        created_at=book.created_at.isoformat(),
    )


@router.get("/books/{book_id}/sections")
def get_book_sections(book_id: str, db: Session = Depends(get_db)):
    """Get all sections for a book."""
    from ..db import Section

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    sections = (
        db.query(Section)
        .filter(Section.book_id == book_id)
        .order_by(Section.order_index)
        .all()
    )

    return {
        "book_id": book_id,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "section_type": s.section_type,
                "order_index": s.order_index,
                "char_start": s.char_start,
                "char_end": s.char_end,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "token_estimate": s.token_estimate,
                "reading_time_min": s.reading_time_min,
            }
            for s in sections
        ],
    }
