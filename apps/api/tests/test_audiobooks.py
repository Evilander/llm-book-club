"""Integration tests for local audiobook playback and synced progress."""

from pathlib import Path
from unittest.mock import patch
import base64

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient
from mutagen.id3 import APIC, ID3

from app.db.models import AudiobookListeningState, Base
from app.services.audiobooks import clear_audiobook_caches
from app.services.media_library import clear_media_catalog_memory


@pytest.fixture
def audiobook_db():
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
def audiobook_client(audiobook_db):
    with patch("app.main.init_db"):
        from app.db import get_db
        from app.main import app
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            yield audiobook_db

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=True) as test_client:
            yield test_client
        app.dependency_overrides.clear()
        limiter.enabled = True


@pytest.fixture(autouse=True)
def clear_audio_catalogs():
    clear_media_catalog_memory()
    clear_audiobook_caches()
    yield
    clear_media_catalog_memory()
    clear_audiobook_caches()


def make_audio_library(root: Path) -> tuple[Path, Path, Path]:
    audiobook = root / "Ada Vale - The Moonlit Archive"
    audiobook.mkdir(parents=True)
    second = audiobook / "02 - Into the Stacks.mp3"
    tenth = audiobook / "10 - The Last Card.mp3"
    solo = root / "A Solo Lecture.m4b"
    second.write_bytes(b"0123456789" * 300)
    tenth.write_bytes(b"abcdefghij" * 300)
    cover = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
        "ASsJTYQAAAAASUVORK5CYII="
    )
    tags = ID3()
    tags.add(APIC(mime="image/png", type=3, desc="cover", data=cover))
    tags.save(tenth)
    solo.write_bytes(b"solo" * 800)
    return second, tenth, solo


def audio_settings(root: Path, profile: str = "listener"):
    from app.routers import audiobooks

    return (
        patch.object(audiobooks.settings, "books_dir", str(root)),
        patch.object(audiobooks.settings, "audiobooks_dir", None),
        patch.object(audiobooks.settings, "app_env", "test"),
        patch.object(audiobooks.settings, "reader_profile_id", profile),
    )


def test_audiobook_library_falls_back_to_books_dir_and_groups_tracks(
    audiobook_client: TestClient,
    tmp_path: Path,
):
    root = tmp_path / "books"
    root.mkdir()
    make_audio_library(root)

    patches = audio_settings(root)
    with patches[0], patches[1], patches[2], patches[3]:
        response = audiobook_client.get("/v1/audiobooks")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["inherited_from_books"] is True
    assert payload["total_tracks"] == 3
    assert payload["total"] == 2
    grouped = next(book for book in payload["audiobooks"] if book["track_count"] == 2)
    assert grouped["title"] == "Ada Vale - The Moonlit Archive"
    assert grouped["source_kind"] == "folder"


def test_manifest_naturally_orders_tracks_and_streams_ranges(
    audiobook_client: TestClient,
    tmp_path: Path,
):
    root = tmp_path / "books"
    root.mkdir()
    make_audio_library(root)

    patches = audio_settings(root)
    with patches[0], patches[1], patches[2], patches[3]:
        listing = audiobook_client.get(
            "/v1/audiobooks", params={"search": "Moonlit Archive"}
        )
        audiobook = listing.json()["audiobooks"][0]
        manifest = audiobook_client.get(f"/v1/audiobooks/{audiobook['id']}")
        first_track = manifest.json()["tracks"][0]
        ranged = audiobook_client.get(
            first_track["stream_url"], headers={"Range": "bytes=10-19"}
        )
        cover = audiobook_client.get(f"/v1/audiobooks/{audiobook['id']}/cover")
        missing = audiobook_client.get(
            f"/v1/audiobooks/{audiobook['id']}/tracks/missing/stream"
        )

    assert manifest.status_code == 200, manifest.text
    tracks = manifest.json()["tracks"]
    assert [track["filename"] for track in tracks] == [
        "02 - Into the Stacks.mp3",
        "10 - The Last Card.mp3",
    ]
    assert tracks[0]["stream_url"].startswith("/v1/audiobooks/")
    assert ranged.status_code == 206
    assert ranged.content == b"0123456789"
    assert ranged.headers["accept-ranges"] == "bytes"
    assert ranged.headers["content-type"].startswith("audio/mpeg")
    assert cover.status_code == 200
    assert cover.headers["content-type"] == "image/png"
    assert cover.headers["content-security-policy"] == "sandbox; default-src 'none'"
    assert missing.status_code == 404


def test_audiobook_match_returns_the_group_not_individual_tracks(
    audiobook_client: TestClient,
    tmp_path: Path,
):
    root = tmp_path / "books"
    root.mkdir()
    make_audio_library(root)

    patches = audio_settings(root)
    with patches[0], patches[1], patches[2], patches[3]:
        response = audiobook_client.get(
            "/v1/audiobooks/matches",
            params={"title": "The Moonlit Archive", "author": "Ada Vale"},
        )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["track_count"] == 2
    assert response.json()[0]["match_score"] >= 0.7


def test_listening_state_round_trips_and_rejects_foreign_tracks(
    audiobook_client: TestClient,
    audiobook_db,
    tmp_path: Path,
):
    root = tmp_path / "books"
    root.mkdir()
    make_audio_library(root)

    patches = audio_settings(root, "cross-browser-listener")
    with patches[0], patches[1], patches[2], patches[3]:
        listing = audiobook_client.get(
            "/v1/audiobooks", params={"search": "Moonlit Archive"}
        )
        audiobook_id = listing.json()["audiobooks"][0]["id"]
        manifest = audiobook_client.get(f"/v1/audiobooks/{audiobook_id}").json()
        current_track = manifest["tracks"][1]
        initial = audiobook_client.get(f"/v1/audiobooks/{audiobook_id}/state")
        saved = audiobook_client.put(
            f"/v1/audiobooks/{audiobook_id}/state",
            json={
                "current_track_id": current_track["id"],
                "position_seconds": 73.5,
                "duration_seconds": 240,
                "playback_rate": 1.35,
                "completed": False,
            },
        )
        loaded = audiobook_client.get(f"/v1/audiobooks/{audiobook_id}/state")
        recent = audiobook_client.get("/v1/audiobooks/recent")
        invalid = audiobook_client.put(
            f"/v1/audiobooks/{audiobook_id}/state",
            json={
                "current_track_id": "not-from-this-book",
                "position_seconds": 1,
                "playback_rate": 1,
            },
        )

    assert initial.status_code == 200
    assert initial.json()["persisted"] is False
    assert saved.status_code == 200, saved.text
    assert saved.json()["track_index"] == 1
    assert saved.json()["position_seconds"] == 73.5
    assert saved.json()["playback_rate"] == 1.35
    assert loaded.json() == saved.json()
    assert recent.json()["books"][0]["audiobook_id"] == audiobook_id
    assert invalid.status_code == 400
    assert audiobook_db.query(AudiobookListeningState).count() == 1
