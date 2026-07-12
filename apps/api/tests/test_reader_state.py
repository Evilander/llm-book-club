"""Integration tests for server-backed reading state and annotations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.models import Base, PublicationReadingState, ReaderAnnotation


@pytest.fixture
def reader_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def reader_client(reader_db):
    with patch("app.main.init_db"):
        from app.db import get_db
        from app.main import app
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            yield reader_db

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
        app.dependency_overrides.clear()
        limiter.enabled = True


def publication_payload(path: Path, title: str = "A Reader Test") -> dict:
    return {
        "file_path": str(path),
        "title": title,
        "author": "Ada Reader",
        "extension": path.suffix.lstrip("."),
        "reader_kind": "foliate",
        "can_discuss": True,
        "book_id": None,
        "ingest_status": None,
    }


def state_payload(path: Path, *, fraction: float = 0.42) -> dict:
    return {
        **publication_payload(path),
        "location": {
            "fraction": fraction,
            "cfi": "epubcfi(/6/4!/4/2/2:10)",
            "chapter": "Chapter 3",
        },
        "preferences": {
            "theme": "night",
            "flow": "scrolled",
            "fontSize": 20,
            "lineHeight": 1.8,
            "maxWidth": 720,
        },
    }


def test_reader_state_round_trip_and_recent_shelf(
    reader_client: TestClient,
    reader_db,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    publication = books_dir / "Reader Test.epub"
    publication.write_bytes(b"publication" * 200)

    from app.routers import reader_state

    with patch.object(reader_state.settings, "books_dir", str(books_dir)), patch.object(
        reader_state.settings, "reader_profile_id", "test-reader"
    ):
        empty = reader_client.get(
            "/v1/reader/state", params={"file_path": str(publication)}
        )
        saved = reader_client.put("/v1/reader/state", json=state_payload(publication))
        loaded = reader_client.get(
            "/v1/reader/state", params={"file_path": str(publication)}
        )
        recent = reader_client.get("/v1/reader/recent")

    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] is None
    assert empty.json()["preferences"]["theme"] == "paper"
    assert saved.status_code == 200, saved.text
    assert saved.json()["state"]["fraction"] == pytest.approx(0.42)
    assert saved.json()["state"]["location"]["cfi"].startswith("epubcfi")
    assert loaded.json()["preferences"]["theme"] == "night"
    assert recent.json()["books"][0]["file_path"] == str(publication.resolve())
    assert reader_db.query(PublicationReadingState).count() == 1


def test_reader_preferences_follow_profile_to_an_unopened_book(
    reader_client: TestClient,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    first = books_dir / "First.epub"
    second = books_dir / "Second.epub"
    first.write_bytes(b"first" * 300)
    second.write_bytes(b"second" * 300)

    from app.routers import reader_state

    with patch.object(reader_state.settings, "books_dir", str(books_dir)), patch.object(
        reader_state.settings, "reader_profile_id", "preferences-reader"
    ):
        saved = reader_client.put("/v1/reader/state", json=state_payload(first))
        unopened = reader_client.get(
            "/v1/reader/state", params={"file_path": str(second)}
        )

    assert saved.status_code == 200, saved.text
    assert unopened.status_code == 200, unopened.text
    assert unopened.json()["state"] is None
    assert unopened.json()["preferences"]["theme"] == "night"
    assert unopened.json()["preferences"]["fontSize"] == 20


def test_annotations_sync_and_tombstones_prevent_stale_resurrection(
    reader_client: TestClient,
    reader_db,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    publication = books_dir / "Marked.epub"
    publication.write_bytes(b"marked" * 300)
    annotation_id = "12345678-1234-4234-8234-123456789abc"
    annotation = {
        "publication": publication_payload(publication, "Marked"),
        "kind": "highlight",
        "quote": "A line worth keeping",
        "note": "The rhythm changes here.",
        "fraction": 0.3,
        "chapter": "Chapter 2",
        "target": {
            "kind": "foliate",
            "cfi": "epubcfi(/6/4!/4/2/2,/1:0,/1:20)",
        },
        "created_at": "2026-01-01T12:00:00Z",
        "updated_at": "2026-01-01T12:00:00Z",
    }

    from app.routers import reader_state

    with patch.object(reader_state.settings, "books_dir", str(books_dir)), patch.object(
        reader_state.settings, "reader_profile_id", "annotation-reader"
    ):
        created = reader_client.put(
            f"/v1/reader/annotations/{annotation_id}", json=annotation
        )
        deleted = reader_client.delete(
            f"/v1/reader/annotations/{annotation_id}",
            params={"file_path": str(publication)},
        )
        stale_retry = reader_client.put(
            f"/v1/reader/annotations/{annotation_id}", json=annotation
        )
        loaded = reader_client.get(
            "/v1/reader/state", params={"file_path": str(publication)}
        )

    assert created.status_code == 200, created.text
    assert created.json()["target"]["cfi"].startswith("epubcfi")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] is not None
    assert stale_retry.status_code == 200, stale_retry.text
    assert stale_retry.json()["deleted_at"] is not None
    assert loaded.json()["annotations"][0]["deleted_at"] is not None
    assert reader_db.query(ReaderAnnotation).count() == 1


def test_reader_state_rejects_paths_outside_library(
    reader_client: TestClient,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    outside = tmp_path / "outside.epub"
    outside.write_bytes(b"outside" * 300)

    from app.routers import reader_state

    with patch.object(reader_state.settings, "books_dir", str(books_dir)):
        response = reader_client.get(
            "/v1/reader/state", params={"file_path": str(outside)}
        )

    assert response.status_code == 403
