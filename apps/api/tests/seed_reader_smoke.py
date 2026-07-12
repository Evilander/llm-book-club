"""Seed one completed real-library book for the browser passage-handoff smoke test."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.db import Book, Chunk, IngestStatus, Section, SessionLocal
from app.db.init_db import init_db


FOCUS_QUOTE = (
    "According to the Nielsen ratings data, 5.019 million people saw me lose my mind."
)


def main() -> None:
    publication = Path(os.environ["LBC_TEST_EPUB"]).resolve()
    init_db()
    db = SessionLocal()
    try:
        book = Book(
            id=str(uuid.uuid4()),
            title="10% Happier",
            author="Dan Harris",
            filename=publication.name,
            file_type="epub",
            file_size_bytes=publication.stat().st_size,
            ingest_status=IngestStatus.COMPLETED,
            metadata_json={"source_path": str(publication)},
        )
        section = Section(
            id=str(uuid.uuid4()),
            book_id=book.id,
            title="Chapter 1: Air Hunger",
            section_type="chapter",
            order_index=0,
            char_start=0,
            char_end=len(FOCUS_QUOTE),
            reading_time_min=8,
            token_estimate=40,
        )
        chunk = Chunk(
            id=str(uuid.uuid4()),
            book_id=book.id,
            section_id=section.id,
            order_index=0,
            text=FOCUS_QUOTE,
            char_start=0,
            char_end=len(FOCUS_QUOTE),
            token_count=20,
            source_ref="Chapter 1",
        )
        db.add_all([book, section, chunk])
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
