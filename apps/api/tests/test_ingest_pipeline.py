"""Tests for worker-side ingestion pipeline metadata."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch
import pytest

from app.db.models import Book, IngestStatus
from app.ingest.extractor import ExtractedBook, ExtractedSection


class FakeEmbeddingsClient:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 3071 for _ in texts]


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


@pytest.mark.parametrize("vectors", [[], [[0.1] * 768], [[float('nan')] * 3072], [[0.0] * 3072]])
def test_incomplete_or_invalid_embeddings_never_complete_a_book(mock_db, vectors):
    from app.ingest import pipeline

    book = Book(title="Fixture", filename="fixture.txt", file_type="txt", file_size_bytes=200, ingest_status=IngestStatus.QUEUED)
    mock_db.add(book)
    mock_db.commit()
    async def embed(_texts):
        return vectors
    client = FakeEmbeddingsClient()
    client.embed = embed
    with patch.object(pipeline, "SessionLocal", return_value=mock_db), patch.object(
        pipeline, "get_embeddings_client", return_value=client
    ), patch.object(mock_db, "close"):
        with pytest.raises(ValueError, match="embedding provider"):
            asyncio.run(pipeline.run_ingestion_pipeline(book.id, b"The cartographer carried an amber compass into the garden.", "fixture.txt"))
    assert mock_db.get(Book, book.id).ingest_status == IngestStatus.FAILED


def test_blank_document_does_not_call_the_embedding_provider(mock_db):
    from app.ingest import pipeline

    book = Book(title="Blank", filename="blank.txt", file_type="txt", file_size_bytes=3, ingest_status=IngestStatus.QUEUED)
    mock_db.add(book)
    mock_db.commit()
    with patch.object(pipeline, "SessionLocal", return_value=mock_db), patch.object(
        pipeline, "get_embeddings_client"
    ) as provider, patch.object(mock_db, "close"):
        with pytest.raises(ValueError, match="No readable text"):
            asyncio.run(pipeline.run_ingestion_pipeline(book.id, b"   ", "blank.txt"))
        provider.assert_not_called()
    assert mock_db.get(Book, book.id).ingest_status == IngestStatus.FAILED
