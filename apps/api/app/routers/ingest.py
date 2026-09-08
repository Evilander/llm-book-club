"""Book ingestion endpoints."""
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..settings import settings
from ..db import Book, BookMemory, DiscussionSession, IngestStatus, ReadingUnit, Section, get_db
from ..ingest.pipeline import STORAGE_DIR
from ..services.media_library import SUPPORTED_AUDIOBOOK_EXTENSIONS, match_audiobooks_for_book, scan_media_dir
from ..worker import enqueue_ingestion_from_path
from ..rate_limit import limiter

router = APIRouter(tags=["ingest"])


async def _store_upload_file(upload: UploadFile, *, size_limit: int) -> tuple[int, Path]:
    filename = upload.filename or "upload.bin"
    ext = Path(filename).suffix.lower()
    file_path = STORAGE_DIR / f"{uuid.uuid4()}{ext}"
    total_bytes = 0

    try:
        with file_path.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > size_limit:
                    raise HTTPException(400, f"File too large. Max size: {settings.max_upload_mb}MB")
                handle.write(chunk)
    except Exception:
        if file_path.exists():
            file_path.unlink()
        raise
    finally:
        await upload.close()

    return total_bytes, file_path


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
    stage: str | None = None
    stage_started_at: str | None = None
    created_at: str
    # Enriched metadata for library browse
    section_count: int = 0
    session_count: int = 0
    last_session_at: str | None = None
    has_audiobook: bool = False
    reading_progress_pct: float | None = None
    current_unit_title: str | None = None
    units_completed: int | None = None
    total_units: int | None = None
    last_read_at: str | None = None

    model_config = {"from_attributes": True}


class BookListResponse(BaseModel):
    books: list[BookResponse]
    total: int


def _book_stage_metadata(book: Book) -> tuple[str | None, str | None]:
    if not isinstance(book.metadata_json, dict):
        return None, None
    stage = book.metadata_json.get("stage")
    stage_started_at = book.metadata_json.get("stage_started_at")
    return (
        stage if isinstance(stage, str) else None,
        stage_started_at if isinstance(stage_started_at, str) else None,
    )


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("3/minute")
async def ingest_book(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF or EPUB file to ingest into the system.

    The file will be processed asynchronously:
    1. Text extraction
    2. Section detection
    3. Chunking
    4. Embedding generation
    """
    # Validate file type
    filename = file.filename or "unknown"
    if not filename.lower().endswith((".pdf", ".epub", ".txt")):
        raise HTTPException(400, "Only PDF, EPUB, and TXT files are supported")

    # Store to disk incrementally to avoid loading the full upload into memory
    size_limit = settings.max_upload_mb * 1024 * 1024
    size_bytes, stored_path = await _store_upload_file(file, size_limit=size_limit)

    # Determine file type
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        file_type = "pdf"
    elif lower_name.endswith(".epub"):
        file_type = "epub"
    else:
        file_type = "txt"

    # Create book record
    book = Book(
        title=filename.rsplit(".", 1)[0],  # Use filename as initial title
        filename=filename,
        file_type=file_type,
        file_size_bytes=size_bytes,
        ingest_status=IngestStatus.QUEUED,
        metadata_json={"ingest_source": "upload", "stored_path": str(stored_path)},
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    # Enqueue ingestion job
    job_id = enqueue_ingestion_from_path(book.id, str(stored_path), filename)

    return IngestResponse(
        book_id=book.id,
        filename=filename,
        bytes=size_bytes,
        status="queued",
        job_id=job_id,
    )


@router.get("/books", response_model=BookListResponse)
def list_books(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    include_audiobook_pairing: bool = False,
    db: Session = Depends(get_db),
):
    """List all books in the library with enriched metadata for browse.

    Optional ``status`` filter restricts to a single ingest_status value
    (e.g. ``completed``). This matters once the library grows past the
    default 50-row page: without filtering, freshly-queued books crowd
    out completed ones and the daylight shelf appears empty.

    Audiobook pairing scan (walking the configured AUDIOBOOKS_DIR) is
    OPT-IN via ``include_audiobook_pairing=true``. On large libraries
    (20k+ audiobooks) the first cold scan can block the shelf for tens of
    seconds; the home page should fetch books without pairing data and
    overlay audiobook badges from a separate lazy call.
    """
    query = db.query(Book).order_by(Book.created_at.desc())
    if status:
        query = query.filter(Book.ingest_status == status)
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

    # Check audiobook availability (OPT-IN only — see docstring).
    has_audiobook: dict[str, bool] = {}
    if include_audiobook_pairing and settings.audiobooks_dir:
        try:
            audiobook_entries = scan_media_dir(
                settings.audiobooks_dir,
                extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
            )
            for b in books:
                if b.ingest_status == IngestStatus.COMPLETED:
                    matches = match_audiobooks_for_book(
                        book_title=b.title,
                        book_author=b.author,
                        audiobook_entries=audiobook_entries,
                    )
                    has_audiobook[b.id] = len(matches) > 0
        except Exception:
            pass  # Graceful degradation if audiobook matching fails

    progress_by_book: dict[str, dict] = {}
    if book_ids:
        memories = (
            db.query(BookMemory)
            .filter(BookMemory.book_id.in_(book_ids))
            .all()
        )
        memories_by_book = {memory.book_id: memory for memory in memories}

        unit_counts: dict[str, int] = {}
        current_units: dict[str, str] = {}
        if book_ids:
            rows = (
                db.query(ReadingUnit.book_id, func.count(ReadingUnit.id))
                .filter(ReadingUnit.book_id.in_(book_ids))
                .group_by(ReadingUnit.book_id)
                .all()
            )
            unit_counts = {book_id: count for book_id, count in rows}

        current_unit_ids = [memory.current_unit_id for memory in memories if memory.current_unit_id]
        if current_unit_ids:
            rows = (
                db.query(ReadingUnit.id, ReadingUnit.title)
                .filter(ReadingUnit.id.in_(current_unit_ids))
                .all()
            )
            current_units = {unit_id: title for unit_id, title in rows}

        for book_id, memory in memories_by_book.items():
            total_units = unit_counts.get(book_id, 0)
            completed_count = len(memory.units_completed or [])
            progress_by_book[book_id] = {
                "reading_progress_pct": (completed_count / total_units * 100) if total_units > 0 else 0.0,
                "current_unit_title": current_units.get(memory.current_unit_id) if memory.current_unit_id else None,
                "units_completed": completed_count,
                "total_units": total_units,
                "last_read_at": memory.last_read_at.isoformat() if memory.last_read_at else None,
            }

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
                stage=_book_stage_metadata(b)[0],
                stage_started_at=_book_stage_metadata(b)[1],
                created_at=b.created_at.isoformat(),
                section_count=section_counts.get(b.id, 0),
                session_count=session_counts.get(b.id, 0),
                last_session_at=last_session_dates.get(b.id),
                has_audiobook=has_audiobook.get(b.id, False),
                reading_progress_pct=progress_by_book.get(b.id, {}).get("reading_progress_pct"),
                current_unit_title=progress_by_book.get(b.id, {}).get("current_unit_title"),
                units_completed=progress_by_book.get(b.id, {}).get("units_completed"),
                total_units=progress_by_book.get(b.id, {}).get("total_units"),
                last_read_at=progress_by_book.get(b.id, {}).get("last_read_at"),
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

    stage, stage_started_at = _book_stage_metadata(book)
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
        stage=stage,
        stage_started_at=stage_started_at,
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
