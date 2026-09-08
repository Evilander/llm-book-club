"""Integration tests for library browsing and book exploration endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.models import (
    Base,
    Book,
    BookMemory,
    Chunk,
    DiscussionMode,
    DiscussionSession,
    IngestStatus,
    Message,
    MessageRole,
    ReadingUnit,
    ReadingUnitType,
    Section,
)
from app.services.media_library import clear_scan_cache


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
    unit = ReadingUnit(
        id=str(uuid.uuid4()),
        book_id=book.id,
        title="Chapter 1",
        unit_type=ReadingUnitType.CHAPTER,
        order_index=0,
        char_start=0,
        char_end=250,
        estimated_reading_min=12,
    )
    integration_db.add(unit)
    integration_db.add(
        BookMemory(
            id=str(uuid.uuid4()),
            book_id=book.id,
            current_unit_id=unit.id,
            units_completed=[],
        )
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
    assert data["progress"]["current_unit_title"] == "Chapter 1"
    assert data["progress"]["resume_section_title"] == "Chapter 1"


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


def test_stream_local_audiobook_serves_configured_file(client: TestClient, tmp_path: Path):
    audiobooks_dir = tmp_path / "audio"
    audiobooks_dir.mkdir()
    audio_file = audiobooks_dir / "Archive Nights.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")

    from app.routers import library as library_router

    with patch.object(library_router.settings, "audiobooks_dir", str(audiobooks_dir)):
        response = client.get(
            "/v1/library/local/audiobooks/stream",
            params={"path": str(audio_file)},
        )

    assert response.status_code == 200
    assert response.content == b"fake-mp3-bytes"
    assert response.headers["content-type"].startswith("audio/mpeg")


def test_stream_local_audiobook_supports_range_requests(client: TestClient, tmp_path: Path):
    audiobooks_dir = tmp_path / "audio"
    audiobooks_dir.mkdir()
    audio_file = audiobooks_dir / "Archive Nights.mp3"
    audio_file.write_bytes(b"fake-mp3-bytes")

    from app.routers import library as library_router

    with patch.object(library_router.settings, "audiobooks_dir", str(audiobooks_dir)):
        response = client.get(
            "/v1/library/local/audiobooks/stream",
            params={"path": str(audio_file)},
            headers={"Range": "bytes=0-3"},
        )

    assert response.status_code == 206
    assert response.content == b"fake"
    assert response.headers["content-range"].startswith("bytes 0-3/")


def test_stream_local_audiobook_refuses_path_escape(client: TestClient, tmp_path: Path):
    audiobooks_dir = tmp_path / "audio"
    audiobooks_dir.mkdir()
    outside_file = tmp_path / "outside.mp3"
    outside_file.write_bytes(b"nope")

    from app.routers import library as library_router

    with patch.object(library_router.settings, "audiobooks_dir", str(audiobooks_dir)):
        response = client.get(
            "/v1/library/local/audiobooks/stream",
            params={"path": str(outside_file)},
        )

    assert response.status_code == 403


def test_list_local_books_uses_cached_scan(client: TestClient, tmp_path: Path):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    (books_dir / "Archive Nights.epub").write_bytes(b"x" * 4096)

    from app.routers import library as library_router

    clear_scan_cache()
    try:
        with patch.object(library_router.settings, "books_dir", str(books_dir)), patch(
            "app.services.media_library.os.walk",
            return_value=[(str(books_dir), [], ["Archive Nights.epub"])],
        ) as mocked_walk:
            first = client.get("/v1/library/local")
            second = client.get("/v1/library/local")

        assert first.status_code == 200
        assert second.status_code == 200
        assert mocked_walk.call_count == 1
    finally:
        clear_scan_cache()


def test_local_library_folders_and_folder_filtered_books(client: TestClient):
    from app.routers import library as library_router

    book_entries = [
        {
            "path": r"D:\books\Fiction & Literature\Glass Botanist.epub",
            "filename": "Glass Botanist.epub",
            "extension": "epub",
            "size_bytes": 2048,
            "title_guess": "Glass Botanist",
            "parent_folder": "Fiction & Literature",
        },
        {
            "path": r"D:\books\Fiction & Literature\Voss Inheritance.epub",
            "filename": "Voss Inheritance.epub",
            "extension": "epub",
            "size_bytes": 4096,
            "title_guess": "Voss Inheritance",
            "parent_folder": "Fiction & Literature",
        },
        {
            "path": r"D:\books\Fiction & Literature\Orchid House.pdf",
            "filename": "Orchid House.pdf",
            "extension": "pdf",
            "size_bytes": 8192,
            "title_guess": "Orchid House",
            "parent_folder": "Fiction & Literature",
        },
        {
            "path": r"D:\books\Journalism\Glass Essays.epub",
            "filename": "Glass Essays.epub",
            "extension": "epub",
            "size_bytes": 1024,
            "title_guess": "Glass Essays",
            "parent_folder": "Journalism",
        },
        {
            "path": r"D:\books\Loose Manual.txt",
            "filename": "Loose Manual.txt",
            "extension": "txt",
            "size_bytes": 1536,
            "title_guess": "Loose Manual",
            "parent_folder": None,
        },
    ]
    audiobook_entries = [
        {
            "path": r"D:\books\Fiction & Literature\Glass Botanist.m4b",
            "filename": "Glass Botanist.m4b",
            "extension": "m4b",
            "size_bytes": 12345,
            "title_guess": "Glass Botanist",
            "parent_folder": "Fiction & Literature",
        },
        {
            "path": r"D:\books\Journalism\Dispatches.mp3",
            "filename": "Dispatches.mp3",
            "extension": "mp3",
            "size_bytes": 67890,
            "title_guess": "Dispatches",
            "parent_folder": "Journalism",
        },
    ]

    with patch.object(library_router.settings, "books_dir", r"D:\books"), patch.object(
        library_router.settings, "audiobooks_dir", r"D:\books"
    ), patch(
        "app.routers.library._scan_local_books",
        return_value=book_entries,
    ) as scan_books, patch(
        "app.routers.library._scan_local_audiobooks",
        return_value=audiobook_entries,
    ) as scan_audio:
        folders = client.get("/v1/library/local/folders")
        fiction_glass = client.get(
            "/v1/library/local",
            params={"folder": "Fiction & Literature", "search": "glass"},
        )

    assert folders.status_code == 200
    folder_payload = folders.json()
    assert folder_payload["books_dir"] == r"D:\books"
    assert folder_payload["total_books"] == 5
    assert folder_payload["root_book_count"] == 1
    assert folder_payload["folders"][0] == {
        "name": "Fiction & Literature",
        "path": r"D:\books\Fiction & Literature",
        "book_count": 3,
        "audiobook_count": 1,
        "sample_titles": [
            "Glass Botanist.epub",
            "Voss Inheritance.epub",
            "Orchid House.pdf",
        ],
    }
    assert folder_payload["folders"][1]["name"] == "Journalism"
    assert folder_payload["folders"][1]["book_count"] == 1
    assert folder_payload["folders"][1]["audiobook_count"] == 1

    assert fiction_glass.status_code == 200
    filtered_payload = fiction_glass.json()
    assert filtered_payload["total"] == 1
    assert filtered_payload["books"][0]["filename"] == "Glass Botanist.epub"
    assert filtered_payload["books"][0]["parent_folder"] == "Fiction & Literature"
    assert scan_books.call_count == 2
    assert scan_audio.call_count == 1


def test_local_ingest_uses_local_limit_not_upload_limit(client: TestClient, tmp_path: Path):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    large_book = books_dir / "Very Large Book.epub"
    large_book.write_bytes(b"x" * 2 * 1024 * 1024)

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)), patch.object(
        library_router.settings, "max_upload_mb", 1
    ), patch.object(library_router.settings, "local_ingest_max_mb", 0), patch(
        "app.routers.library.enqueue_ingestion_from_path",
        return_value="job-123",
    ) as enqueue_mock:
        response = client.post(
            "/v1/library/local/ingest",
            json={"file_path": str(large_book)},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "Very Large Book.epub"
    enqueue_mock.assert_called_once()


def test_ingest_folder_queues_unindexed_books_and_skips_existing(
    client: TestClient,
    integration_db,
    tmp_path: Path,
):
    books_dir = tmp_path / "books"
    folder = books_dir / "Fiction & Literature"
    folder.mkdir(parents=True)
    entries = []
    for index in range(6):
        path = folder / f"Volume {index}.epub"
        path.write_bytes(b"x" * 4096)
        entries.append(
            {
                "path": str(path),
                "filename": path.name,
                "extension": "epub",
                "size_bytes": 4096,
                "title_guess": f"Volume {index}",
                "parent_folder": "Fiction & Literature",
            }
        )

    existing = Book(
        id=str(uuid.uuid4()),
        title="Volume 0",
        filename="Volume 0.epub",
        file_type="epub",
        file_size_bytes=4096,
        ingest_status=IngestStatus.COMPLETED,
        metadata_json={"source_path": entries[0]["path"]},
    )
    integration_db.add(existing)
    integration_db.commit()

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)), patch.object(
        library_router.settings, "local_ingest_max_mb", 0
    ), patch(
        "app.routers.library._scan_local_books",
        return_value=entries,
    ), patch(
        "app.routers.library.enqueue_ingestion_from_path",
        return_value="job-123",
    ) as enqueue_mock:
        response = client.post(
            "/v1/library/local/ingest_folder",
            json={"folder": "Fiction & Literature", "limit": 5},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["folder"] == "Fiction & Literature"
    assert payload["total_in_folder"] == 6
    assert payload["already_ingested_count"] == 1
    assert payload["queued_count"] == 5
    assert len(payload["queued_book_ids"]) == 5
    assert payload["skipped_oversize"] == []
    assert enqueue_mock.call_count == 5

    queued = (
        integration_db.query(Book)
        .filter(Book.ingest_status == IngestStatus.QUEUED)
        .order_by(Book.filename)
        .all()
    )
    assert [book.filename for book in queued] == [f"Volume {index}.epub" for index in range(1, 6)]


def test_ingest_folder_enforces_cap_and_direct_child_path(client: TestClient, tmp_path: Path):
    books_dir = tmp_path / "books"
    (books_dir / "Fiction & Literature").mkdir(parents=True)

    from app.routers import library as library_router

    with patch.object(library_router.settings, "books_dir", str(books_dir)):
        capped = client.post(
            "/v1/library/local/ingest_folder",
            json={"folder": "Fiction & Literature", "limit": 600},
        )
        traversal = client.post(
            "/v1/library/local/ingest_folder",
            json={"folder": "../etc", "limit": 1},
        )

    assert capped.status_code == 400
    assert "multiple requests" in capped.json()["detail"]
    assert traversal.status_code in {400, 403}


def test_bindery_pause_status_is_idempotent(client: TestClient, integration_db):
    from app.routers import library as library_router

    state = {"paused": False}
    now = datetime.utcnow()
    integration_db.add_all(
        [
            Book(
                id=str(uuid.uuid4()),
                title="Queued",
                filename="queued.epub",
                file_type="epub",
                file_size_bytes=4096,
                ingest_status=IngestStatus.QUEUED,
            ),
            Book(
                id=str(uuid.uuid4()),
                title="Processing",
                filename="processing.epub",
                file_type="epub",
                file_size_bytes=4096,
                ingest_status=IngestStatus.PROCESSING,
            ),
            Book(
                id=str(uuid.uuid4()),
                title="Fresh Failure",
                filename="fresh-failure.epub",
                file_type="epub",
                file_size_bytes=4096,
                ingest_status=IngestStatus.FAILED,
                updated_at=now,
            ),
            Book(
                id=str(uuid.uuid4()),
                title="Old Failure",
                filename="old-failure.epub",
                file_type="epub",
                file_size_bytes=4096,
                ingest_status=IngestStatus.FAILED,
                updated_at=now - timedelta(days=2),
            ),
        ]
    )
    integration_db.commit()

    def fake_set_bindery_paused(paused: bool) -> bool:
        state["paused"] = paused
        return paused

    with patch.object(library_router, "set_bindery_paused", side_effect=fake_set_bindery_paused), patch.object(
        library_router, "is_bindery_paused", side_effect=lambda: state["paused"]
    ):
        initial = client.get("/v1/library/bindery/status")
        pause = client.post("/v1/library/bindery/pause", json={"paused": True})
        pause_again = client.post("/v1/library/bindery/pause", json={"paused": True})
        resumed = client.post("/v1/library/bindery/pause", json={"paused": False})

    assert initial.status_code == 200
    assert initial.json() == {"paused": False, "queued": 1, "processing": 1, "failed_recent": 1}
    assert pause.status_code == 200
    assert pause.json() == {"paused": True, "queued": 1, "processing": 1, "failed_recent": 1}
    assert pause_again.status_code == 200
    assert pause_again.json()["paused"] is True
    assert resumed.status_code == 200
    assert resumed.json() == {"paused": False, "queued": 1, "processing": 1, "failed_recent": 1}


def test_retry_failed_book_requeues_local_source(client: TestClient, integration_db, tmp_path: Path):
    source = tmp_path / "Retry Me.epub"
    source.write_bytes(b"x" * 4096)
    book = Book(
        id=str(uuid.uuid4()),
        title="Retry Me",
        filename="Retry Me.epub",
        file_type="epub",
        file_size_bytes=4096,
        ingest_status=IngestStatus.FAILED,
        ingest_error="embedding service timed out",
        metadata_json={
            "source_path": str(source),
            "stage": "failed",
            "stage_started_at": "2026-05-12T00:00:00",
        },
    )
    integration_db.add(book)
    integration_db.commit()

    with patch("app.routers.library.enqueue_ingestion_from_path", return_value="job-123") as enqueue_mock:
        response = client.post(f"/v1/books/{book.id}/retry")

    integration_db.refresh(book)
    assert response.status_code == 200
    assert response.json() == {
        "book_id": book.id,
        "filename": "Retry Me.epub",
        "size_bytes": 4096,
        "status": "queued",
    }
    assert book.ingest_status == IngestStatus.QUEUED
    assert book.ingest_error is None
    assert "stage" not in book.metadata_json
    assert "stage_started_at" not in book.metadata_json
    enqueue_mock.assert_called_once_with(book.id, str(source), "Retry Me.epub")


def test_retry_rejects_non_failed_book(client: TestClient, integration_db, tmp_path: Path):
    source = tmp_path / "Already Fine.epub"
    source.write_bytes(b"x" * 4096)
    book = Book(
        id=str(uuid.uuid4()),
        title="Already Fine",
        filename="Already Fine.epub",
        file_type="epub",
        file_size_bytes=4096,
        ingest_status=IngestStatus.COMPLETED,
        metadata_json={"source_path": str(source)},
    )
    integration_db.add(book)
    integration_db.commit()

    response = client.post(f"/v1/books/{book.id}/retry")

    assert response.status_code == 422
    assert "failed" in response.json()["detail"]


def test_retry_without_source_path_requires_fresh_upload(client: TestClient, integration_db):
    book = Book(
        id=str(uuid.uuid4()),
        title="No Source",
        filename="no-source.epub",
        file_type="epub",
        file_size_bytes=4096,
        ingest_status=IngestStatus.FAILED,
        ingest_error="lost original file",
        metadata_json={"stage": "failed"},
    )
    integration_db.add(book)
    integration_db.commit()

    response = client.post(f"/v1/books/{book.id}/retry")

    assert response.status_code == 422
    assert "source_path" in response.json()["detail"]


def test_retry_missing_book_returns_404(client: TestClient):
    response = client.post(f"/v1/books/{uuid.uuid4()}/retry")

    assert response.status_code == 404


def test_library_search_mixes_ingested_and_library_results_in_score_order(
    client: TestClient,
    integration_db,
):
    book = Book(
        id=str(uuid.uuid4()),
        title="Glass Botanist",
        author="Ada Vale",
        filename="glass-botanist.epub",
        file_type="epub",
        file_size_bytes=4096,
        ingest_status=IngestStatus.COMPLETED,
    )
    integration_db.add(book)
    integration_db.commit()

    from app.routers import library as library_router

    library_entries = [
        {
            "path": r"D:\books\Fiction & Literature\Glass Botanist Field Notes.epub",
            "filename": "Glass Botanist Field Notes.epub",
            "extension": "epub",
            "size_bytes": 8192,
            "title_guess": "Glass Botanist Field Notes",
            "parent_folder": "Fiction & Literature",
        },
        {
            "path": r"D:\books\Glass Botanist Studies\Unrelated.pdf",
            "filename": "Unrelated.pdf",
            "extension": "pdf",
            "size_bytes": 1024,
            "title_guess": "Unrelated",
            "parent_folder": "Glass Botanist Studies",
        },
    ]
    audiobook_entries = [
        {
            "path": r"D:\books\Fiction & Literature\Glass Botanist.m4b",
            "filename": "Glass Botanist.m4b",
            "extension": "m4b",
            "size_bytes": 2048,
            "title_guess": "Glass Botanist",
            "parent_folder": "Fiction & Literature",
        }
    ]

    with patch.object(library_router.settings, "books_dir", r"D:\books"), patch(
        "app.routers.library._scan_local_books",
        return_value=library_entries,
    ), patch(
        "app.routers.library._scan_local_audiobooks",
        return_value=audiobook_entries,
    ):
        response = client.get("/v1/library/search", params={"q": "Glass Botanist"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Glass Botanist"
    assert payload["total"] == 3
    assert payload["ingested_count"] == 1
    assert payload["library_count"] == 2
    assert [item["score"] for item in payload["results"]] == [100, 80, 20]
    assert payload["results"][0]["source"] == "ingested"
    assert payload["results"][0]["book_id"] == book.id
    assert payload["results"][1]["source"] == "library"
    assert payload["results"][1]["audiobook_count"] == 1


def test_reader_page_returns_first_and_last_page_then_404(client: TestClient, integration_db):
    book = Book(
        id=str(uuid.uuid4()),
        title="Long Reader",
        author="Ada Vale",
        filename="long-reader.epub",
        file_type="epub",
        file_size_bytes=4096,
        ingest_status=IngestStatus.COMPLETED,
    )
    integration_db.add(book)
    integration_db.flush()

    first_text = "alpha " * 120
    second_text = "omega " * 80
    first_section = Section(
        id=str(uuid.uuid4()),
        book_id=book.id,
        title="First",
        section_type="chapter",
        order_index=0,
        char_start=0,
        char_end=len(first_text),
    )
    second_section = Section(
        id=str(uuid.uuid4()),
        book_id=book.id,
        title="Second",
        section_type="chapter",
        order_index=1,
        char_start=len(first_text),
        char_end=len(first_text) + len(second_text),
    )
    integration_db.add_all([first_section, second_section])
    integration_db.flush()
    integration_db.add_all(
        [
            Chunk(
                id=str(uuid.uuid4()),
                book_id=book.id,
                section_id=first_section.id,
                order_index=0,
                text=first_text,
                char_start=0,
                char_end=len(first_text),
            ),
            Chunk(
                id=str(uuid.uuid4()),
                book_id=book.id,
                section_id=second_section.id,
                order_index=0,
                text=second_text,
                char_start=len(first_text),
                char_end=len(first_text) + len(second_text),
            ),
        ]
    )
    integration_db.commit()

    first = client.get(f"/v1/books/{book.id}/reader", params={"page": 1, "page_size": 400})
    last = client.get(f"/v1/books/{book.id}/reader", params={"page": 4, "page_size": 400})
    missing = client.get(f"/v1/books/{book.id}/reader", params={"page": 5, "page_size": 400})

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["title"] == "Long Reader"
    assert first_payload["total_chars"] == len(first_text + "\n\n" + second_text)
    assert first_payload["total_pages"] == 4
    assert first_payload["current_section_title"] == "First"
    assert first_payload["char_start"] == 0
    assert first_payload["char_end"] == first_payload["char_start"] + len(first_payload["text"])
    assert len(first_payload["text"]) <= 400

    assert last.status_code == 200
    last_payload = last.json()
    assert last_payload["page"] == 4
    assert last_payload["current_section_title"] == "Second"
    assert last_payload["char_end"] == first_payload["total_chars"]
    assert len(last_payload["text"]) <= 400
    assert missing.status_code == 404


def test_list_books_surfaces_progress_summary(client: TestClient, populated_book: Book):
    response = client.get("/v1/books")

    assert response.status_code == 200
    payload = response.json()
    book = payload["books"][0]
    assert book["title"] == "The Moonlit Archive"
    assert book["current_unit_title"] == "Chapter 1"
    assert book["reading_progress_pct"] == 0.0


def test_section_progress_route_maps_section_to_reading_unit(
    client: TestClient,
    populated_book: Book,
):
    explore = client.get(f"/v1/books/{populated_book.id}/explore").json()
    section_id = explore["sections"][0]["id"]

    response = client.post(
        f"/v1/memory/books/{populated_book.id}/sections/{section_id}/progress",
        json={"status": "completed", "time_spent_min": 15},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["reading_unit_title"] == "Chapter 1"

    memory = client.get(f"/v1/memory/books/{populated_book.id}").json()
    assert memory["current_unit_id"] == payload["reading_unit_id"]
    assert memory["reading_progress_pct"] == 100.0


def test_book_marginalia_returns_recent_agent_notes(
    client: TestClient,
    integration_db,
    populated_book: Book,
):
    section = integration_db.query(Section).filter(Section.book_id == populated_book.id).first()
    session = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=populated_book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="discussion",
        is_active=True,
        created_at=datetime.utcnow() - timedelta(minutes=10),
        updated_at=datetime.utcnow() - timedelta(minutes=1),
    )
    integration_db.add(session)
    integration_db.flush()

    integration_db.add_all(
        [
            Message(
                id=str(uuid.uuid4()),
                session_id=session.id,
                role=MessageRole.FACILITATOR,
                content="Start with what the room refuses to name. Then ask who benefits from the quiet.",
                created_at=datetime.utcnow() - timedelta(seconds=3),
            ),
            Message(
                id=str(uuid.uuid4()),
                session_id=session.id,
                role=MessageRole.CLOSE_READER,
                content="The image pattern keeps narrowing. Glass turns the room into a witness.",
                created_at=datetime.utcnow() - timedelta(seconds=2),
            ),
            Message(
                id=str(uuid.uuid4()),
                session_id=session.id,
                role=MessageRole.SKEPTIC,
                content="That reading still needs pressure. Maybe the audience is the point.",
                created_at=datetime.utcnow() - timedelta(seconds=1),
            ),
        ]
    )
    integration_db.commit()

    response = client.get(f"/v1/memory/books/{populated_book.id}/marginalia")

    assert response.status_code == 200
    payload = response.json()
    assert payload["book_id"] == populated_book.id
    assert payload["section_id"] == section.id

    notes = {item["agent"]: item for item in payload["marginalia"]}
    assert notes["sam"]["name"] == "Sam"
    assert notes["ellis"]["name"] == "Ellis"
    assert notes["kit"]["name"] == "Kit"
    assert notes["sam"]["note"] == "Then ask who benefits from the quiet"
    assert notes["ellis"]["note"] == "The image pattern keeps narrowing"
    assert notes["kit"]["note"] == "Maybe the audience is the point"
    assert all(item["note"] is not None and len(item["note"]) <= 140 for item in notes.values())


def test_book_marginalia_skips_citation_sentences_and_allows_missing_roles(
    client: TestClient,
    integration_db,
    populated_book: Book,
):
    section = integration_db.query(Section).filter(Section.book_id == populated_book.id).first()
    session = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=populated_book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="discussion",
        is_active=True,
    )
    integration_db.add(session)
    integration_db.flush()
    integration_db.add(
        Message(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=MessageRole.FACILITATOR,
            content="The first claim leans on chunk:8a4f evidence. The clean margin survives.",
        )
    )
    integration_db.commit()

    response = client.get(f"/v1/memory/books/{populated_book.id}/marginalia")

    assert response.status_code == 200
    notes = {item["agent"]: item for item in response.json()["marginalia"]}
    assert notes["sam"]["note"] == "The clean margin survives"
    assert notes["ellis"]["note"] is None
    assert notes["kit"]["note"] is None
