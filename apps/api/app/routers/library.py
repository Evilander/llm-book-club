"""Library endpoints for browsing books, exploring text, and pairing local audio."""

from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import Book, Chunk, IngestStatus, Section, get_db
from ..rate_limit import limiter
from ..services.media_library import (
    CATALOG_VERSION,
    SUPPORTED_AUDIOBOOK_EXTENSIONS,
    SUPPORTED_DISCUSSION_EXTENSIONS,
    SUPPORTED_READER_EXTENSIONS,
    find_media_catalog_item,
    get_media_catalog,
    guess_title,
)
from ..services.catalog_index import get_or_seed_catalog, scan_and_index_catalog
from ..services.audiobooks import (
    audiobook_summary,
    grouped_audiobook_catalog,
    match_audiobook_groups,
    search_audiobooks,
)
from ..services.publication_assets import (
    get_publication_cover,
    get_publication_details,
    public_publication_details,
)
from ..settings import settings
from ..worker import enqueue_local_ingestion

router = APIRouter(tags=["library"])


class LocalBookEntry(BaseModel):
    id: str
    path: str
    filename: str
    extension: str
    format_family: str
    reader_kind: str
    can_discuss: bool = False
    size_bytes: int
    modified_at: str
    title_guess: str
    parent_folder: str | None = None
    already_ingested: bool = False
    book_id: str | None = None
    ingest_status: str | None = None
    ingest_error: str | None = None


class LocalLibraryResponse(BaseModel):
    books_dir: str
    total: int
    books: list[LocalBookEntry]
    catalog_total: int
    discussion_capable_total: int
    format_counts: dict[str, int] = Field(default_factory=dict)
    indexed_at: str
    scan_duration_ms: int


class LocalLibraryRefreshResponse(BaseModel):
    catalog_total: int
    indexed_at: str
    scan_duration_ms: int


class LocalPublicationDetailsRequest(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=50)


class LocalPublicationDetails(BaseModel):
    id: str
    title: str | None = None
    author: str | None = None
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = None
    language: str | None = None
    series: str | None = None
    series_index: str | None = None
    description: str | None = None
    has_cover: bool = False


class LocalPublicationDetailsResponse(BaseModel):
    publications: list[LocalPublicationDetails]
    missing_ids: list[str] = Field(default_factory=list)


class LocalAudiobookEntry(BaseModel):
    id: str | None = None
    path: str
    filename: str
    extension: str
    size_bytes: int
    title_guess: str
    parent_folder: str | None = None
    modified_at: str | None = None
    match_score: float | None = None
    match_reason: str | None = None
    track_count: int = 1
    source_kind: str = "file"


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


_READER_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".mobi": "application/x-mobipocket-ebook",
    ".azw": "application/vnd.amazon.ebook",
    ".azw3": "application/vnd.amazon.ebook",
    ".prc": "application/x-mobipocket-ebook",
    ".fb2": "application/x-fictionbook+xml",
    ".cbz": "application/vnd.comicbook+zip",
    ".txt": "text/plain; charset=utf-8",
}


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


def resolve_library_path(root_dir: str | None, file_path: Path) -> Path:
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


def _retry_failed_local_ingestion(
    db: Session, book: Book, source_path: Path, filename: str
) -> None:
    if book.ingest_status != IngestStatus.FAILED:
        return
    book.ingest_status = IngestStatus.QUEUED
    book.ingest_error = None
    db.commit()
    enqueue_local_ingestion(book.id, str(source_path), filename)


def _catalog_cache_file(kind: str) -> Path | None:
    # Tests use temporary roots and should never leave derived snapshots in the
    # source tree. Production/dev storage is a persisted Docker volume.
    if settings.app_env == "test":
        return None
    return Path(settings.storage_dir) / "catalog" / f"{kind}-v{CATALOG_VERSION}.json"


def _local_books_catalog(db: Session, *, force_refresh: bool = False) -> dict:
    if not settings.books_dir:
        return get_media_catalog(None, extensions=SUPPORTED_READER_EXTENSIONS)
    if force_refresh and settings.media_catalog_index_enabled:
        return scan_and_index_catalog(
            db,
            root_dir=settings.books_dir,
            kind="books",
            extensions=SUPPORTED_READER_EXTENSIONS,
            cache_file=_catalog_cache_file("books"),
        )
    if force_refresh:
        return get_media_catalog(
            settings.books_dir,
            extensions=SUPPORTED_READER_EXTENSIONS,
            cache_file=_catalog_cache_file("books"),
            ttl_seconds=settings.library_catalog_ttl,
            force_refresh=True,
        )
    return get_or_seed_catalog(
        db,
        root_dir=settings.books_dir,
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
        index_enabled=settings.media_catalog_index_enabled,
        cache_file=_catalog_cache_file("books"),
        ttl_seconds=settings.library_catalog_ttl,
    )


def _publication_cache_dir() -> Path:
    return Path(settings.storage_dir) / "publication-assets"


def _local_catalog_entry(db: Session, media_id: str) -> dict | None:
    return find_media_catalog_item(_local_books_catalog(db), media_id)

def _effective_audiobooks_dir() -> str | None:
    return settings.audiobooks_dir or settings.books_dir


def _local_audiobook_catalog(db: Session) -> dict:
    root = _effective_audiobooks_dir()
    if not root:
        return get_media_catalog(None, extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS)
    return get_or_seed_catalog(
        db,
        root_dir=root,
        kind="audiobooks",
        extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
        index_enabled=settings.media_catalog_index_enabled,
        cache_file=_catalog_cache_file("audiobooks"),
        ttl_seconds=settings.library_catalog_ttl,
    )


def _scan_local_audiobooks(db: Session) -> list[dict]:
    return grouped_audiobook_catalog(_local_audiobook_catalog(db))


def _lookup_ingested_books(
    db: Session,
    entries: list[dict],
) -> dict[str, dict[str, str | None]]:
    if not entries:
        return {}

    filenames = {entry["filename"] for entry in entries}
    rows = db.query(Book).filter(Book.filename.in_(filenames)).all()

    rows_by_filename: dict[str, list[Book]] = {}
    for row in rows:
        rows_by_filename.setdefault(row.filename, []).append(row)

    matched: dict[str, dict[str, str | None]] = {}
    for entry in entries:
        entry_path = entry["path"]
        candidates = rows_by_filename.get(entry["filename"], [])
        for row in candidates:
            source_path = None
            if isinstance(row.metadata_json, dict):
                source_path = row.metadata_json.get("source_path")
            if source_path and source_path == entry_path:
                matched[entry_path] = {
                    "book_id": str(row.id),
                    "ingest_status": row.ingest_status.value,
                    "ingest_error": row.ingest_error,
                }
                break

        # Uploaded books created before source_path existed can still match by
        # filename, but only when the filename is unambiguous.
        if entry_path not in matched and len(candidates) == 1:
            row = candidates[0]
            source_path = (
                row.metadata_json.get("source_path")
                if isinstance(row.metadata_json, dict)
                else None
            )
            if not source_path:
                matched[entry_path] = {
                    "book_id": str(row.id),
                    "ingest_status": row.ingest_status.value,
                    "ingest_error": row.ingest_error,
                }

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
    format_filter: str | None = Query(None, alias="format"),
    sort: str = "title",
    order: str = "asc",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if not settings.books_dir:
        raise HTTPException(
            400,
            "BOOKS_DIR not configured. Set the BOOKS_DIR environment variable to your books folder path.",
        )

    if skip < 0:
        raise HTTPException(400, "skip must be zero or greater")
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    if sort not in {"title", "modified", "size"}:
        raise HTTPException(400, "sort must be title, modified, or size")
    if order not in {"asc", "desc"}:
        raise HTTPException(400, "order must be asc or desc")

    catalog = _local_books_catalog(db)
    catalog_files = catalog["items"]
    all_files = catalog_files

    if extension:
        ext = extension.lower().lstrip(".")
        all_files = [item for item in all_files if item["extension"] == ext]

    if format_filter:
        family = format_filter.lower()
        valid_families = {"epub", "pdf", "kindle", "comic", "text"}
        if family not in valid_families:
            raise HTTPException(
                400,
                "format must be epub, pdf, kindle, comic, or text",
            )
        all_files = [item for item in all_files if item["format_family"] == family]

    if search:
        search_lower = search.casefold().strip()
        all_files = [
            item
            for item in all_files
            if search_lower in item["filename"].casefold()
            or search_lower in item["title_guess"].casefold()
            or search_lower in item.get("parent_folder", "").casefold()
        ]

    sort_key = {
        "title": lambda item: item["title_guess"].casefold(),
        "modified": lambda item: item["modified_at"],
        "size": lambda item: item["size_bytes"],
    }[sort]
    all_files = sorted(all_files, key=sort_key, reverse=order == "desc")

    total = len(all_files)
    page = all_files[skip : skip + limit]
    ingested_by_path = _lookup_ingested_books(db, page)
    format_counts = Counter(item["format_family"] for item in catalog_files)

    return LocalLibraryResponse(
        books_dir=settings.books_dir,
        total=total,
        catalog_total=len(catalog_files),
        discussion_capable_total=sum(
            1 for item in catalog_files if item["can_discuss"]
        ),
        format_counts=dict(format_counts),
        indexed_at=catalog["indexed_at"],
        scan_duration_ms=catalog["scan_duration_ms"],
        books=[
            LocalBookEntry(
                **entry,
                already_ingested=entry["path"] in ingested_by_path,
                book_id=(ingested_by_path.get(entry["path"]) or {}).get("book_id"),
                ingest_status=(
                    ingested_by_path.get(entry["path"]) or {}
                ).get("ingest_status"),
                ingest_error=(
                    ingested_by_path.get(entry["path"]) or {}
                ).get("ingest_error"),
            )
            for entry in page
        ],
    )


@router.post("/library/local/refresh", response_model=LocalLibraryRefreshResponse)
@limiter.limit("6/minute")
def refresh_local_library(request: Request, db: Session = Depends(get_db)):
    if not settings.books_dir:
        raise HTTPException(
            400,
            "BOOKS_DIR not configured. Set the BOOKS_DIR environment variable to your books folder path.",
        )
    catalog = _local_books_catalog(db, force_refresh=True)
    return LocalLibraryRefreshResponse(
        catalog_total=len(catalog["items"]),
        indexed_at=catalog["indexed_at"],
        scan_duration_ms=catalog["scan_duration_ms"],
    )


@router.post("/library/local/details", response_model=LocalPublicationDetailsResponse)
@limiter.limit("120/minute")
def local_publication_details(
    request: Request,
    body: LocalPublicationDetailsRequest = Body(...),
    db: Session = Depends(get_db),
):
    publications: list[LocalPublicationDetails] = []
    missing_ids: list[str] = []
    seen: set[str] = set()
    for media_id in body.media_ids:
        if media_id in seen:
            continue
        seen.add(media_id)
        entry = _local_catalog_entry(db, media_id)
        if not entry:
            missing_ids.append(media_id)
            continue
        details = public_publication_details(
            get_publication_details(Path(entry["path"]), _publication_cache_dir())
        )
        publications.append(LocalPublicationDetails(id=media_id, **details))
    return LocalPublicationDetailsResponse(
        publications=publications,
        missing_ids=missing_ids,
    )


@router.api_route("/library/local/{media_id}/cover", methods=["GET", "HEAD"])
@limiter.limit("300/minute")
def local_publication_cover(
    request: Request,
    media_id: str,
    db: Session = Depends(get_db),
):
    entry = _local_catalog_entry(db, media_id)
    if not entry:
        raise HTTPException(404, "Publication not found")
    cover = get_publication_cover(Path(entry["path"]), _publication_cache_dir())
    if not cover:
        raise HTTPException(404, "Publication has no extractable cover")
    cover_path, media_type, etag = cover
    return FileResponse(
        path=cover_path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"{etag}"',
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.get("/library/local/audiobooks", response_model=LocalAudiobookLibraryResponse)
def list_local_audiobooks(
    search: str | None = None,
    extension: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    audiobooks_dir = _effective_audiobooks_dir()
    if not audiobooks_dir:
        raise HTTPException(
            400,
            "Neither AUDIOBOOKS_DIR nor BOOKS_DIR is configured",
        )

    all_files = _scan_local_audiobooks(db)

    if extension:
        ext = extension.lower().lstrip(".")
        all_files = [item for item in all_files if ext in item["extensions"]]

    if search:
        all_files = search_audiobooks(all_files, search)

    total = len(all_files)
    page = all_files[skip : skip + limit]

    return LocalAudiobookLibraryResponse(
        audiobooks_dir=audiobooks_dir,
        total=total,
        books=[LocalAudiobookEntry(**audiobook_summary(entry)) for entry in page],
    )


@router.api_route("/library/local/file", methods=["GET", "HEAD"])
def read_local_book_file(file_path: str):
    """Stream a reader-supported file from the configured library root.

    Starlette's FileResponse provides byte-range handling, which keeps PDF
    navigation efficient and leaves room for a range-aware EPUB loader.
    """
    resolved_path = resolve_library_path(settings.books_dir, Path(file_path))
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(404, "Book file not found")

    extension = resolved_path.suffix.lower()
    if extension not in SUPPORTED_READER_EXTENSIONS:
        raise HTTPException(400, f"Unsupported reader format: {extension}")

    return FileResponse(
        path=resolved_path,
        media_type=_READER_MEDIA_TYPES.get(extension, "application/octet-stream"),
        filename=resolved_path.name,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            # Publications are untrusted documents. The web reader strips
            # scripts as well; this protects top-level/native rendering.
            "Content-Security-Policy": "sandbox; object-src 'none'",
        },
    )


@router.post("/library/local/ingest", response_model=LocalIngestResponse)
@limiter.limit("3/minute")
async def ingest_local_book(
    request: Request,
    body: LocalIngestRequest = Body(...),
    db: Session = Depends(get_db),
):
    resolved_path = resolve_library_path(settings.books_dir, Path(body.file_path))

    if not resolved_path.exists():
        raise HTTPException(404, "File not found")

    ext = resolved_path.suffix.lower()
    if ext not in SUPPORTED_DISCUSSION_EXTENSIONS:
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
        if source_path == str(resolved_path):
            _retry_failed_local_ingestion(db, row, resolved_path, filename)
            return LocalIngestResponse(
                book_id=str(row.id),
                filename=filename,
                size_bytes=size_bytes,
                status=row.ingest_status.value,
            )

    if len(existing) == 1:
        row = existing[0]
        source_path = (
            row.metadata_json.get("source_path")
            if isinstance(row.metadata_json, dict)
            else None
        )
        if not source_path:
            _retry_failed_local_ingestion(db, row, resolved_path, filename)
            return LocalIngestResponse(
                book_id=str(row.id),
                filename=filename,
                size_bytes=size_bytes,
                status=row.ingest_status.value,
            )

    publication_details = public_publication_details(
        get_publication_details(resolved_path, _publication_cache_dir())
    )
    book = Book(
        title=publication_details["title"] or guess_title(filename),
        author=publication_details["author"],
        filename=filename,
        file_type=ext.lstrip("."),
        file_size_bytes=size_bytes,
        ingest_status=IngestStatus.QUEUED,
        metadata_json={
            "ingest_source": "local_library",
            "source_path": str(resolved_path),
            "source_parent": resolved_path.parent.name,
            "publication": publication_details,
        },
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    enqueue_local_ingestion(book.id, str(resolved_path), filename)

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
        for entry in match_audiobook_groups(
            book_title=book.title,
            book_author=book.author,
            audiobooks=_scan_local_audiobooks(db),
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
        audiobooks_dir=_effective_audiobooks_dir(),
    )
