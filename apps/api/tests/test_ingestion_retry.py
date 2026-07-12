"""Idempotency coverage for retrying a partially completed ingestion."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Book, Chunk, IngestStatus, Section
from app.ingest.pipeline import run_ingestion_pipeline
from app.ingest.pipeline import run_local_ingestion_sync


class FakeEmbeddings:
    async def embed(self, texts: list[str]) -> list[None]:
        return [None for _ in texts]


@pytest.mark.asyncio
async def test_retry_replaces_partial_chunks_and_preserves_source_metadata():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    db = sessions()
    book = Book(
        id=str(uuid.uuid4()),
        title="Retry Book",
        filename="retry.txt",
        file_type="txt",
        file_size_bytes=4096,
        ingest_status=IngestStatus.QUEUED,
        metadata_json={"source_path": r"D:\books\retry.txt"},
    )
    db.add(book)
    db.commit()
    book_id = book.id
    filename = book.filename
    db.close()

    text = b"CHAPTER 1 Arrival\n\nThe first section.\n\nCHAPTER 2 Return\n\nThe second section."
    with patch("app.ingest.pipeline.SessionLocal", sessions), patch(
        "app.ingest.pipeline.get_embeddings_client",
        return_value=FakeEmbeddings(),
    ):
        await run_ingestion_pipeline(book_id, text, filename)

        inspection = sessions()
        first_section_count = inspection.query(Section).filter_by(book_id=book_id).count()
        first_chunk_count = inspection.query(Chunk).filter_by(book_id=book_id).count()
        persisted = inspection.query(Book).filter_by(id=book_id).one()
        assert persisted.metadata_json["source_path"] == r"D:\books\retry.txt"
        persisted.ingest_status = IngestStatus.FAILED
        persisted.ingest_error = "retry me"
        inspection.commit()
        inspection.close()

        await run_ingestion_pipeline(book_id, text, filename)

    inspection = sessions()
    retried = inspection.query(Book).filter_by(id=book_id).one()
    assert retried.ingest_status == IngestStatus.COMPLETED
    assert retried.metadata_json["source_path"] == r"D:\books\retry.txt"
    assert inspection.query(Section).filter_by(book_id=book_id).count() == first_section_count
    assert inspection.query(Chunk).filter_by(book_id=book_id).count() == first_chunk_count
    inspection.close()


def test_local_worker_reads_mounted_file_only_when_job_runs(tmp_path):
    publication = tmp_path / "large-book.fb2"
    publication.write_bytes(b"publication bytes")

    with patch(
        "app.ingest.pipeline.run_ingestion_sync",
        return_value="book-id",
    ) as run:
        result = run_local_ingestion_sync(
            "book-id",
            str(publication),
            publication.name,
        )

    assert result == "book-id"
    run.assert_called_once_with("book-id", b"publication bytes", publication.name)
