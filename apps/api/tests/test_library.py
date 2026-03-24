"""Integration tests for library browsing and book exploration endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.models import Base, Book, Chunk, IngestStatus, Section


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
        with TestClient(app, raise_server_exceptions=False) as test_client:
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
