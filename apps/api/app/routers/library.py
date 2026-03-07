"""Local book library endpoints — browse and ingest books from the local filesystem."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..settings import settings
from ..db import get_db, Book, IngestStatus
from ..worker import enqueue_ingestion
from ..rate_limit import limiter

router = APIRouter(tags=["library"])

SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".txt"}


class LocalBookEntry(BaseModel):
    """A book file found on the local filesystem."""
    path: str
    filename: str
    extension: str
    size_bytes: int
    title_guess: str
    already_ingested: bool = False
    book_id: str | None = None


class LocalLibraryResponse(BaseModel):
    books_dir: str
    total: int
    books: list[LocalBookEntry]


class LocalIngestRequest(BaseModel):
    file_path: str


class LocalIngestResponse(BaseModel):
    book_id: str
    filename: str
    size_bytes: int
    status: str


def _guess_title(filename: str) -> str:
    """Guess a readable title from a filename."""
    name = Path(filename).stem
    # Strip common patterns like ISBN, brackets, parentheses at start
    # Keep it simple — just clean up the stem
    name = name.replace("_", " ").replace("-", " ")
    # Collapse multiple spaces
    parts = name.split()
    if parts:
        return " ".join(parts)
    return filename


def _scan_books_dir(books_dir: str) -> list[dict]:
    """Recursively scan a directory for supported book files."""
    results = []
    books_path = Path(books_dir)

    if not books_path.exists():
        return results

    for root, _dirs, files in os.walk(books_path):
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            full_path = os.path.join(root, fname)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue

            # Skip very small files (likely not real books)
            if size < 1024:
                continue

            results.append({
                "path": full_path,
                "filename": fname,
                "extension": ext.lstrip("."),
                "size_bytes": size,
                "title_guess": _guess_title(fname),
            })

    # Sort by filename for consistent ordering
    results.sort(key=lambda x: x["filename"].lower())
    return results


@router.get("/library/local", response_model=LocalLibraryResponse)
def list_local_books(
    search: str | None = None,
    extension: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Scan the local books directory and return available files.

    Marks books that have already been ingested into the system.
    """
    books_dir = settings.books_dir
    if not books_dir:
        raise HTTPException(
            400,
            "BOOKS_DIR not configured. Set the BOOKS_DIR environment variable to your books folder path.",
        )

    all_files = _scan_books_dir(books_dir)

    # Filter by extension
    if extension:
        ext = extension.lower().lstrip(".")
        all_files = [f for f in all_files if f["extension"] == ext]

    # Filter by search term (case-insensitive filename/title match)
    if search:
        search_lower = search.lower()
        all_files = [
            f for f in all_files
            if search_lower in f["filename"].lower()
            or search_lower in f["title_guess"].lower()
        ]

    total = len(all_files)
    page = all_files[skip : skip + limit]

    # Check which files are already ingested (match by filename)
    ingested_filenames = {}
    if page:
        filenames = [f["filename"] for f in page]
        existing = (
            db.query(Book.filename, Book.id)
            .filter(Book.filename.in_(filenames))
            .all()
        )
        ingested_filenames = {row.filename: str(row.id) for row in existing}

    entries = []
    for f in page:
        book_id = ingested_filenames.get(f["filename"])
        entries.append(LocalBookEntry(
            path=f["path"],
            filename=f["filename"],
            extension=f["extension"],
            size_bytes=f["size_bytes"],
            title_guess=f["title_guess"],
            already_ingested=book_id is not None,
            book_id=book_id,
        ))

    return LocalLibraryResponse(
        books_dir=books_dir,
        total=total,
        books=entries,
    )


@router.post("/library/local/ingest", response_model=LocalIngestResponse)
@limiter.limit("3/minute")
async def ingest_local_book(
    request: Request,
    body: LocalIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest a book from the local filesystem by its path.

    The file must be within the configured BOOKS_DIR.
    """
    books_dir = settings.books_dir
    if not books_dir:
        raise HTTPException(400, "BOOKS_DIR not configured")

    file_path = Path(body.file_path)

    # Security: ensure the path is within BOOKS_DIR
    try:
        file_path = file_path.resolve()
        books_dir_resolved = Path(books_dir).resolve()
        if not str(file_path).startswith(str(books_dir_resolved)):
            raise HTTPException(403, "File path is outside the configured books directory")
    except (OSError, ValueError):
        raise HTTPException(400, "Invalid file path")

    if not file_path.exists():
        raise HTTPException(404, "File not found")

    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Check size
    size = file_path.stat().st_size
    size_limit = settings.max_upload_mb * 1024 * 1024
    if size > size_limit:
        raise HTTPException(400, f"File too large ({size / 1024 / 1024:.1f}MB). Max: {settings.max_upload_mb}MB")

    filename = file_path.name
    file_type = ext.lstrip(".")

    # Check if already ingested
    existing = db.query(Book).filter(Book.filename == filename).first()
    if existing:
        return LocalIngestResponse(
            book_id=str(existing.id),
            filename=filename,
            size_bytes=size,
            status=existing.ingest_status.value,
        )

    # Read file and create book record
    data = file_path.read_bytes()

    book = Book(
        title=_guess_title(filename),
        filename=filename,
        file_type=file_type,
        file_size_bytes=size,
        ingest_status=IngestStatus.QUEUED,
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    # Enqueue ingestion
    enqueue_ingestion(book.id, data, filename)

    return LocalIngestResponse(
        book_id=str(book.id),
        filename=filename,
        size_bytes=size,
        status="queued",
    )
