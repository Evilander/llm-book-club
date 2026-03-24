"""Book ingestion endpoints."""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from ..settings import settings
from ..db import get_db, Book, IngestStatus, Section, DiscussionSession
from ..worker import enqueue_ingestion
from ..rate_limit import limiter

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
    # Enriched metadata for library browse
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

    # Read and validate size
    size_limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read()
    if len(data) > size_limit:
        raise HTTPException(400, f"File too large. Max size: {settings.max_upload_mb}MB")

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
        file_size_bytes=len(data),
        ingest_status=IngestStatus.QUEUED,
        metadata_json={"ingest_source": "upload"},
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    # Enqueue ingestion job
    job_id = enqueue_ingestion(book.id, data, filename)

    return IngestResponse(
        book_id=book.id,
        filename=filename,
        bytes=len(data),
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
    if settings.audiobooks_dir:
        try:
            from ..services.media_library import match_audiobooks_for_book
            for b in books:
                if b.ingest_status == IngestStatus.COMPLETED:
                    matches = match_audiobooks_for_book(b.title, b.author)
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
