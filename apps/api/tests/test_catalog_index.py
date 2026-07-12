"""Persistent local-media catalog generation and API contract tests."""

from __future__ import annotations

from pathlib import Path
import os
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.models import Base, LocalMediaCatalog, LocalMediaCatalogItem
from app.services.catalog_index import (
    clear_catalog_index_cache,
    find_catalog,
    get_or_seed_catalog,
    load_catalog_snapshot,
    scan_and_index_catalog,
)
from app.services.media_library import (
    SUPPORTED_AUDIOBOOK_EXTENSIONS,
    SUPPORTED_READER_EXTENSIONS,
    clear_media_catalog_memory,
)


@pytest.fixture(autouse=True)
def clear_catalog_caches():
    clear_catalog_index_cache()
    clear_media_catalog_memory()
    yield
    clear_catalog_index_cache()
    clear_media_catalog_memory()


@pytest.fixture
def catalog_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


@pytest.fixture
def catalog_client(catalog_db):
    with patch("app.main.init_db"):
        from app.db import get_db
        from app.main import app
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            yield catalog_db

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
        app.dependency_overrides.clear()
        limiter.enabled = True


def write_book(path: Path, marker: bytes = b"book") -> None:
    path.write_bytes(marker * 600)


def test_incremental_scan_promotes_complete_generations(catalog_db, tmp_path: Path):
    root = tmp_path / "books"
    root.mkdir()
    first = root / "First.epub"
    removed = root / "Removed.pdf"
    write_book(first, b"first")
    write_book(removed, b"removed")

    initial = scan_and_index_catalog(
        catalog_db,
        root_dir=str(root),
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    first_id = next(item["id"] for item in initial["items"] if item["filename"] == first.name)
    assert initial["generation"] == 1
    assert len(initial["items"]) == 2

    removed.unlink()
    added = root / "Added.azw3"
    write_book(added, b"added")
    write_book(first, b"changed")
    refreshed = scan_and_index_catalog(
        catalog_db,
        root_dir=str(root),
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )

    assert refreshed["generation"] == 2
    assert {item["filename"] for item in refreshed["items"]} == {
        "Added.azw3",
        "First.epub",
    }
    assert next(
        item["id"] for item in refreshed["items"] if item["filename"] == first.name
    ) == first_id
    rows = catalog_db.query(LocalMediaCatalogItem).all()
    assert len(rows) == 3
    assert sum(item.is_available for item in rows) == 2
    assert next(item for item in rows if item.filename == removed.name).is_available is False

    timestamps = {item.id: item.updated_at for item in rows}
    unchanged = scan_and_index_catalog(
        catalog_db,
        root_dir=str(root),
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    catalog_db.expire_all()
    assert unchanged["generation"] == 3
    assert {
        item.id: item.updated_at for item in catalog_db.query(LocalMediaCatalogItem).all()
    } == timestamps


def test_failed_scan_keeps_previous_generation_readable(catalog_db, tmp_path: Path):
    root = tmp_path / "books"
    root.mkdir()
    write_book(root / "Still Here.epub")
    scan_and_index_catalog(
        catalog_db,
        root_dir=str(root),
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    clear_catalog_index_cache()

    with patch(
        "app.services.catalog_index.get_media_catalog",
        side_effect=OSError("simulated interrupted walk"),
    ), pytest.raises(OSError):
        scan_and_index_catalog(
            catalog_db,
            root_dir=str(root),
            kind="books",
            extensions=SUPPORTED_READER_EXTENSIONS,
        )

    previous = load_catalog_snapshot(
        catalog_db,
        root_dir=str(root),
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    catalog = find_catalog(catalog_db, root_dir=str(root), kind="books")
    assert previous is not None
    assert previous["generation"] == 1
    assert [item["filename"] for item in previous["items"]] == ["Still Here.epub"]
    assert catalog is not None
    assert catalog.status == "failed"
    assert catalog.active_generation == 1
    assert "simulated interrupted walk" in (catalog.scan_error or "")


def test_database_snapshot_survives_process_cache_clear(catalog_db, tmp_path: Path):
    root = tmp_path / "books"
    root.mkdir()
    write_book(root / "Persisted.epub")
    scan_and_index_catalog(
        catalog_db,
        root_dir=str(root),
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    clear_catalog_index_cache()
    clear_media_catalog_memory()

    with patch(
        "app.services.catalog_index.get_media_catalog",
        side_effect=AssertionError("filesystem should not be rescanned"),
    ):
        restored = load_catalog_snapshot(
            catalog_db,
            root_dir=str(root),
            kind="books",
            extensions=SUPPORTED_READER_EXTENSIONS,
        )

    assert restored is not None
    assert restored["source"] == "database"
    assert restored["items"][0]["filename"] == "Persisted.epub"


def test_seed_failure_falls_back_to_legacy_snapshot(catalog_db, tmp_path: Path):
    root = tmp_path / "books"
    root.mkdir()
    write_book(root / "Still Readable.epub")

    with patch(
        "app.services.catalog_index.persist_catalog_snapshot",
        side_effect=RuntimeError("database temporarily unavailable"),
    ):
        snapshot = get_or_seed_catalog(
            catalog_db,
            root_dir=str(root),
            kind="books",
            extensions=SUPPORTED_READER_EXTENSIONS,
            index_enabled=True,
        )

    assert snapshot["items"][0]["filename"] == "Still Readable.epub"


def test_catalog_status_enqueue_is_idempotent(
    catalog_client: TestClient,
    catalog_db,
    tmp_path: Path,
):
    root = tmp_path / "books"
    root.mkdir()
    write_book(root / "Queued.epub")

    from app.routers import catalog as catalog_router

    with patch.object(catalog_router.settings, "books_dir", str(root)), patch.object(
        catalog_router.settings, "audiobooks_dir", None
    ), patch.object(
        catalog_router.settings, "media_catalog_index_enabled", True
    ), patch.object(
        catalog_router,
        "enqueue_catalog_scan",
        return_value="ignored-because-id-is-preallocated",
    ) as enqueue:
        before = catalog_client.get("/v1/library/catalog/status")
        first = catalog_client.post(
            "/v1/library/catalog/scans", json={"kind": "books"}
        )
        second = catalog_client.post(
            "/v1/library/catalog/scans", json={"kind": "books"}
        )
        job_id = first.json()["catalogs"][0]["job_id"]
        polled = catalog_client.get(f"/v1/library/catalog/scans/{job_id}")

    assert before.status_code == 200
    assert before.json()["catalogs"][0]["generation"] == 0
    assert first.status_code == 202, first.text
    assert first.json()["catalogs"][0]["status"] == "queued"
    assert second.status_code == 202
    assert second.json()["catalogs"][0]["job_id"] == job_id
    assert polled.status_code == 200
    assert enqueue.call_count == 1
    catalog = catalog_db.query(LocalMediaCatalog).filter_by(kind="books").one()
    assert catalog.status == "queued"


def test_local_scan_falls_back_when_worker_queue_is_offline(
    catalog_client: TestClient,
    tmp_path: Path,
):
    root = tmp_path / "books"
    root.mkdir()
    write_book(root / "Offline Worker.epub")

    from app.routers import catalog as catalog_router

    with patch.object(catalog_router.settings, "books_dir", str(root)), patch.object(
        catalog_router.settings, "audiobooks_dir", str(tmp_path / "missing-audio")
    ), patch.object(
        catalog_router.settings, "media_catalog_index_enabled", True
    ), patch.object(
        catalog_router.settings, "app_env", "dev"
    ), patch.object(
        catalog_router,
        "enqueue_catalog_scan",
        side_effect=ConnectionError("Redis is offline"),
    ), patch.object(catalog_router, "run_catalog_scan") as local_scan:
        response = catalog_client.post(
            "/v1/library/catalog/scans", json={"kind": "books"}
        )

    assert response.status_code == 202, response.text
    assert response.json()["catalogs"][0]["status"] == "queued"
    local_scan.assert_called_once()


@pytest.mark.skipif(
    not os.environ.get("LBC_BENCHMARK_BOOKS_DIR"),
    reason="set LBC_BENCHMARK_BOOKS_DIR for the opt-in real-library benchmark",
)
def test_real_library_index_benchmark(catalog_db):
    root = os.environ["LBC_BENCHMARK_BOOKS_DIR"]
    started = time.perf_counter()
    books = scan_and_index_catalog(
        catalog_db,
        root_dir=root,
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    books_seconds = time.perf_counter() - started

    started = time.perf_counter()
    audio = scan_and_index_catalog(
        catalog_db,
        root_dir=root,
        kind="audiobooks",
        extensions=SUPPORTED_AUDIOBOOK_EXTENSIONS,
    )
    audio_seconds = time.perf_counter() - started

    clear_media_catalog_memory()
    started = time.perf_counter()
    unchanged_books = scan_and_index_catalog(
        catalog_db,
        root_dir=root,
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    unchanged_rescan_seconds = time.perf_counter() - started

    clear_catalog_index_cache()
    catalog_db.expire_all()
    started = time.perf_counter()
    restored = load_catalog_snapshot(
        catalog_db,
        root_dir=root,
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    database_reload_seconds = time.perf_counter() - started
    started = time.perf_counter()
    warm = load_catalog_snapshot(
        catalog_db,
        root_dir=root,
        kind="books",
        extensions=SUPPORTED_READER_EXTENSIONS,
    )
    warm_seconds = time.perf_counter() - started

    metrics = {
        "books": len(books["items"]),
        "audio_tracks": len(audio["items"]),
        "books_scan_and_index_seconds": round(books_seconds, 3),
        "audio_scan_and_index_seconds": round(audio_seconds, 3),
        "unchanged_books_rescan_seconds": round(unchanged_rescan_seconds, 3),
        "database_reload_seconds": round(database_reload_seconds, 3),
        "warm_snapshot_seconds": round(warm_seconds, 6),
    }
    print(f"real catalog benchmark: {metrics}")
    assert len(books["items"]) > 30_000
    assert len(audio["items"]) > 15_000
    assert unchanged_books["generation"] == 2
    assert len(unchanged_books["items"]) == len(books["items"])
    assert restored is not None and warm is restored
    assert database_reload_seconds < 15
    assert warm_seconds < 0.3
