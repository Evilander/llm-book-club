"""Integration tests for library browsing and book exploration endpoints."""

from __future__ import annotations

import uuid
import base64
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.models import Base, Book, Chunk, IngestStatus, Section
from app.services.media_library import (
    SUPPORTED_READER_EXTENSIONS,
    clear_media_catalog_memory,
    get_media_catalog,
)
from app.services.audiobooks import clear_audiobook_caches


@pytest.fixture
def integration_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def integration_db(integration_engine):
    Session = sessionmaker(bind=integration_engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def client(integration_db):
    with patch("app.main.init_db"):
        from app.main import app
        from app.db import get_db
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            try:
                yield integration_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=True) as test_client:
            yield test_client
        app.dependency_overrides.clear()
        limiter.enabled = True


@pytest.fixture
def populated_book(integration_db):
    book = Book(
        id=str(uuid.uuid4()),
        title="The Moonlit Archive",
        author="Ada Vale",
        filename="moonlit-archive.epub",
        file_type="epub",
        file_size_bytes=2048,
        ingest_status=IngestStatus.COMPLETED,
        metadata_json={"source_path": r"D:\books\The Moonlit Archive.epub"},
    )
    integration_db.add(book)
    integration_db.flush()

    section = Section(
        id=str(uuid.uuid4()),
        book_id=book.id,
        title="Chapter 1",
        section_type="chapter",
        order_index=0,
        char_start=0,
        char_end=250,
        reading_time_min=12,
    )
    integration_db.add(section)
    integration_db.flush()

    integration_db.add_all(
        [
            Chunk(
                id=str(uuid.uuid4()),
                book_id=book.id,
                section_id=section.id,
                order_index=0,
                text="Moonlight pressed against the glass while Ada opened the archive.",
                char_start=0,
                char_end=72,
                source_ref="p. 1",
            ),
            Chunk(
                id=str(uuid.uuid4()),
                book_id=book.id,
                section_id=section.id,
                order_index=1,
                text="Inside, the catalog cards smelled like cedar and static electricity.",
                char_start=73,
                char_end=150,
                source_ref="p. 2",
            ),
        ]
    )
    integration_db.commit()
    return book


def test_explore_book_surfaces_section_text_and_audio_match(
    client: TestClient,
    populated_book: Book,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    audiobooks_dir = tmp_path / "audio"
    books_dir.mkdir()
    audiobooks_dir.mkdir()
    (books_dir / "The Moonlit Archive.epub").write_bytes(b"x" * 2048)
    (audiobooks_dir / "The Moonlit Archive - Ada Vale.m4b").write_bytes(b"x" * 4096)

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)), patch.object(
        library_router.settings, "audiobooks_dir", str(audiobooks_dir)
    ):
        response = client.get(f"/v1/books/{populated_book.id}/explore")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "The Moonlit Archive"
    assert data["active_section"]["text"].startswith("Moonlight pressed against the glass")
    assert data["has_local_audiobook"] is True
    assert data["audiobook_matches"][0]["title_guess"].startswith("The Moonlit Archive")


def test_list_local_audiobooks_reads_configured_library(client: TestClient, tmp_path: Path):
    audiobooks_dir = tmp_path / "audio"
    audiobooks_dir.mkdir()
    (audiobooks_dir / "Archive Nights.m4b").write_bytes(b"x" * 4096)

    from app.routers import library as library_router

    with patch.object(library_router.settings, "audiobooks_dir", str(audiobooks_dir)):
        response = client.get("/v1/library/local/audiobooks")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["books"][0]["extension"] == "m4b"


def test_ingested_books_detect_colocated_audiobook_groups(
    client: TestClient,
    populated_book: Book,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    audio_dir = books_dir / "Ada Vale - The Moonlit Archive"
    audio_dir.mkdir(parents=True)
    (audio_dir / "01 - Opening.mp3").write_bytes(b"x" * 4096)
    (audio_dir / "02 - Archive.mp3").write_bytes(b"x" * 4096)

    from app.routers import ingest as ingest_router

    clear_media_catalog_memory()
    clear_audiobook_caches()
    with patch.object(ingest_router.settings, "books_dir", str(books_dir)), patch.object(
        ingest_router.settings, "audiobooks_dir", None
    ), patch.object(ingest_router.settings, "app_env", "test"):
        response = client.get("/v1/books")

    assert response.status_code == 200, response.text
    payload = response.json()
    book = next(item for item in payload["books"] if item["id"] == populated_book.id)
    assert book["has_audiobook"] is True


def test_local_catalog_is_persisted_until_explicit_refresh(tmp_path: Path):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "First.epub").write_bytes(b"x" * 2048)
    cache_file = tmp_path / "catalog.json"

    clear_media_catalog_memory()
    first = get_media_catalog(
        str(books_dir),
        extensions=SUPPORTED_READER_EXTENSIONS,
        cache_file=cache_file,
        ttl_seconds=3600,
    )
    assert len(first["items"]) == 1
    assert cache_file.exists()

    (books_dir / "Second.mobi").write_bytes(b"x" * 2048)
    cached = get_media_catalog(
        str(books_dir),
        extensions=SUPPORTED_READER_EXTENSIONS,
        cache_file=cache_file,
        ttl_seconds=3600,
    )
    assert len(cached["items"]) == 1

    refreshed = get_media_catalog(
        str(books_dir),
        extensions=SUPPORTED_READER_EXTENSIONS,
        cache_file=cache_file,
        ttl_seconds=3600,
        force_refresh=True,
    )
    assert {item["extension"] for item in refreshed["items"]} == {"epub", "mobi"}


def test_list_local_books_includes_reader_formats_and_family_filter(
    client: TestClient,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "A Novel.epub").write_bytes(b"x" * 2048)
    (books_dir / "Old Kindle.mobi").write_bytes(b"x" * 4096)
    (books_dir / "Panels.cbz").write_bytes(b"x" * 8192)

    from app.routers import library as library_router

    clear_media_catalog_memory()
    with patch.object(library_router.settings, "books_dir", str(books_dir)):
        response = client.get("/v1/library/local?format=kindle")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["catalog_total"] == 3
    assert data["discussion_capable_total"] == 2
    assert data["total"] == 1
    assert data["format_counts"] == {"epub": 1, "kindle": 1, "comic": 1}
    kindle = data["books"][0]
    assert kindle["reader_kind"] == "foliate"
    assert kindle["can_discuss"] is True


def test_local_file_stream_supports_ranges_and_blocks_escape(
    client: TestClient,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    book_path = books_dir / "Range Test.epub"
    book_path.write_bytes(b"0123456789" * 300)
    outside_path = tmp_path / "outside.epub"
    outside_path.write_bytes(b"outside")

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)):
        ranged = client.get(
            "/v1/library/local/file",
            params={"file_path": str(book_path)},
            headers={"Range": "bytes=10-19"},
        )
        escaped = client.get(
            "/v1/library/local/file",
            params={"file_path": str(outside_path)},
        )

    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"
    assert ranged.headers["accept-ranges"] == "bytes"
    assert ranged.headers["content-type"].startswith("application/epub+zip")
    assert escaped.status_code == 403


def test_local_publication_details_and_cover_use_catalog_ids(
    client: TestClient,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    storage_dir = tmp_path / "storage"
    books_dir.mkdir()
    publication = books_dir / "opaque-name.epub"
    cover_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
        "ASsJTYQAAAAASUVORK5CYII="
    )
    with zipfile.ZipFile(publication, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="book.opf" />'
            "</rootfiles></container>",
        )
        archive.writestr(
            "book.opf",
            "<package><metadata><title>Catalog of Small Stars</title>"
            "<creator>Iris North</creator></metadata><manifest>"
            '<item id="cover" href="cover.png" media-type="image/png" '
            'properties="cover-image" /></manifest></package>',
        )
        archive.writestr("cover.png", cover_bytes)
        archive.writestr("padding.txt", "x" * 2048)

    from app.routers import library as library_router

    clear_media_catalog_memory()
    with patch.object(library_router.settings, "books_dir", str(books_dir)), patch.object(
        library_router.settings, "storage_dir", str(storage_dir)
    ):
        listing = client.get("/v1/library/local")
        media_id = listing.json()["books"][0]["id"]
        details = client.post(
            "/v1/library/local/details",
            json={"media_ids": [media_id, "missing"]},
        )
        cover = client.get(f"/v1/library/local/{media_id}/cover")
        missing_cover = client.get("/v1/library/local/missing/cover")

    assert details.status_code == 200, details.text
    payload = details.json()
    assert payload["publications"][0]["title"] == "Catalog of Small Stars"
    assert payload["publications"][0]["author"] == "Iris North"
    assert payload["publications"][0]["has_cover"] is True
    assert payload["missing_ids"] == ["missing"]
    assert cover.status_code == 200
    assert cover.content == cover_bytes
    assert cover.headers["content-type"] == "image/png"
    assert cover.headers["content-security-policy"] == "sandbox; default-src 'none'"
    assert missing_cover.status_code == 404


def test_local_ingest_does_not_confuse_duplicate_filenames(
    client: TestClient,
    integration_db,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    first_dir = books_dir / "first"
    second_dir = books_dir / "second"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first_path = first_dir / "Shared Title.epub"
    second_path = second_dir / "Shared Title.epub"
    first_path.write_bytes(b"a" * 2048)
    second_path.write_bytes(b"b" * 2048)

    existing = Book(
        title="Shared Title",
        filename=first_path.name,
        file_type="epub",
        file_size_bytes=first_path.stat().st_size,
        ingest_status=IngestStatus.COMPLETED,
        metadata_json={"source_path": str(first_path.resolve())},
    )
    integration_db.add(existing)
    integration_db.commit()

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)), patch.object(
        library_router, "enqueue_local_ingestion", return_value="job-id"
    ):
        response = client.post(
            "/v1/library/local/ingest",
            json={"file_path": str(second_path)},
        )

    assert response.status_code == 200, response.text
    assert response.json()["book_id"] != existing.id
    assert integration_db.query(Book).filter(Book.filename == first_path.name).count() == 2


def test_failed_local_ingest_retries_by_path_without_copying_file_into_queue(
    client: TestClient,
    integration_db,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    publication = books_dir / "Retry This.azw3"
    publication.write_bytes(b"mobi-data" * 300)
    failed = Book(
        title="Retry This",
        filename=publication.name,
        file_type="azw3",
        file_size_bytes=publication.stat().st_size,
        ingest_status=IngestStatus.FAILED,
        ingest_error="temporary embedding failure",
        metadata_json={"source_path": str(publication.resolve())},
    )
    integration_db.add(failed)
    integration_db.commit()

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)), patch.object(
        library_router, "enqueue_local_ingestion", return_value="retry-job"
    ) as enqueue:
        response = client.post(
            "/v1/library/local/ingest",
            json={"file_path": str(publication)},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    integration_db.refresh(failed)
    assert failed.ingest_status == IngestStatus.QUEUED
    assert failed.ingest_error is None
    enqueue.assert_called_once_with(
        failed.id,
        str(publication.resolve()),
        publication.name,
    )


@pytest.mark.parametrize("extension", ["fb2", "mobi", "azw", "azw3", "prc"])
def test_upload_accepts_extended_discussion_formats(
    client: TestClient,
    integration_db,
    extension: str,
):
    from app.routers import ingest as ingest_router

    file_data = b"publication-data" * 150
    filename = f"Reader Edition.{extension}"
    with patch.object(ingest_router, "enqueue_ingestion", return_value="job-id") as enqueue:
        response = client.post(
            "/v1/ingest",
            files={"file": (filename, file_data, "application/octet-stream")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    book = integration_db.get(Book, payload["book_id"])
    assert book is not None
    assert book.file_type == extension
    enqueue.assert_called_once_with(book.id, file_data, filename)


def test_upload_rejects_read_only_comic_format(
    client: TestClient,
    integration_db,
):
    from app.routers import ingest as ingest_router

    with patch.object(ingest_router, "enqueue_ingestion") as enqueue:
        response = client.post(
            "/v1/ingest",
            files={"file": ("Comic.cbz", b"comic-data" * 150, "application/zip")},
        )

    assert response.status_code == 400
    assert integration_db.query(Book).count() == 0
    enqueue.assert_not_called()
