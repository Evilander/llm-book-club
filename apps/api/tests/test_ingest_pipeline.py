"""Tests for worker-side ingestion pipeline metadata."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

from app.db.models import Book, IngestStatus
from app.ingest.extractor import ExtractedBook, ExtractedSection


class FakeEmbeddingsClient:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return []


def test_ingestion_pipeline_writes_bindery_stages(mock_db):
    from app.ingest import pipeline

    book = Book(
        id=str(uuid.uuid4()),
        title="Queued Book",
        filename="queued.epub",
        file_type="epub",
        file_size_bytes=2048,
        ingest_status=IngestStatus.QUEUED,
        metadata_json={"ingest_source": "test"},
    )
    mock_db.add(book)
    mock_db.commit()
    book_id = book.id

    extracted = ExtractedBook(
        title="Queued Book",
        author="Ada Vale",
        file_type="epub",
        full_text="Chapter text with enough words to become a small chunk.",
        sections=[
            ExtractedSection(
                title="Chapter 1",
                section_type="chapter",
                order_index=0,
                text="Chapter text with enough words to become a small chunk.",
                char_start=0,
                char_end=55,
            )
        ],
        metadata={"source": "fixture"},
    )

    stages_seen: list[str] = []
    original_commit = mock_db.commit

    def record_commit():
        current = mock_db.get(Book, book_id)
        if isinstance(current.metadata_json, dict) and current.metadata_json.get("stage"):
            stages_seen.append(current.metadata_json["stage"])
        return original_commit()

    with patch.object(pipeline, "SessionLocal", return_value=mock_db), patch.object(
        pipeline, "extract_text", return_value=extracted
    ), patch.object(
        pipeline, "get_embeddings_client", return_value=FakeEmbeddingsClient()
    ), patch.object(
        mock_db, "commit", side_effect=record_commit
    ), patch.object(
        mock_db, "close", return_value=None
    ):
        asyncio.run(pipeline.run_ingestion_pipeline(book_id, b"fake", "queued.epub"))

    current = mock_db.get(Book, book_id)
    collapsed_stages = []
    for stage in stages_seen:
        if not collapsed_stages or collapsed_stages[-1] != stage:
            collapsed_stages.append(stage)

    assert collapsed_stages[:6] == [
        "extracting",
        "setting_type",
        "sewing",
        "embedding",
        "drying",
        "shelved",
    ]
    assert current.ingest_status == IngestStatus.COMPLETED
    assert current.metadata_json["stage"] == "shelved"
    assert current.metadata_json["stage_started_at"]
