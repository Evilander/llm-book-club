"""Shared test fixtures for the LLM Book Club test suite.

Sets up environment variables, patches pgvector for SQLite compatibility,
and provides reusable fixtures for the test database and sample data.
"""
import os
import sys
import uuid

import pytest

# ---------------------------------------------------------------------------
# 1. Environment variables required by app.settings (must be set before any
#    app-level import so that pydantic-settings does not error out).
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("APP_ENV", "test")

# ---------------------------------------------------------------------------
# 2. Patch pgvector.sqlalchemy.Vector before any model import so that the
#    ORM column type degrades gracefully to a Text column in SQLite.
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock
from sqlalchemy import Text as _SAText

_original_vector_module = sys.modules.get("pgvector.sqlalchemy")


class _FakeVector(_SAText):
    """Drop-in replacement for pgvector.sqlalchemy.Vector.

    In tests we use SQLite which does not support the pgvector extension.
    This replaces Vector(dim) with a plain Text column so that
    ``Base.metadata.create_all`` succeeds.
    """

    def __init__(self, dim: int = 3072, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim


class _FakeModule:
    Vector = _FakeVector


sys.modules["pgvector"] = MagicMock()
sys.modules["pgvector.sqlalchemy"] = _FakeModule()

# ---------------------------------------------------------------------------
# 3. Now it is safe to import application code.
# ---------------------------------------------------------------------------
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db.models import (  # noqa: E402
    Base,
    Book,
    Section,
    Chunk,
    DiscussionSession,
    Message,
    IngestStatus,
    DiscussionMode,
    MessageRole,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create an in-memory SQLite database for testing.

    Note: pgvector is not available in SQLite, so the ``embedding`` column on
    Chunk is mapped to a plain Text column (see the patching above).  This is
    sufficient for testing citation verification and other logic that does not
    depend on vector similarity.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def sample_book(mock_db):
    """Create a sample book with one section and five chunks."""
    book = Book(
        id=str(uuid.uuid4()),
        title="Test Book: The Great Novel",
        author="Test Author",
        filename="test.pdf",
        file_type="pdf",
        file_size_bytes=1000,
        ingest_status=IngestStatus.COMPLETED,
    )
    mock_db.add(book)
    mock_db.flush()

    section = Section(
        id=str(uuid.uuid4()),
        book_id=book.id,
        title="Chapter 1: The Beginning",
        section_type="chapter",
        order_index=0,
        char_start=0,
        char_end=500,
    )
    mock_db.add(section)
    mock_db.flush()

    chunk_texts = [
        (
            "The morning sun cast long shadows across the empty courtyard. "
            "Maria stood at the window, watching the last of the autumn "
            "leaves drift down from the old oak tree."
        ),
        (
            "He had always known this day would come. The letter in his "
            "pocket felt heavier than any stone he had ever carried up "
            "the mountain path."
        ),
        (
            "The river wound through the valley like a silver ribbon, its "
            "waters carrying the stories of a thousand years. On its banks, "
            "the willows wept."
        ),
        (
            "She opened the book to the first page and began to read. The "
            "words seemed to leap off the page, alive with meaning she had "
            "never noticed before."
        ),
        (
            "In the quiet of the library, surrounded by the musty smell of "
            "old books, he finally understood what his grandmother had been "
            "trying to tell him all those years."
        ),
    ]

    chunks = []
    for i, text in enumerate(chunk_texts):
        chunk = Chunk(
            id=str(uuid.uuid4()),
            book_id=book.id,
            section_id=section.id,
            order_index=i,
            text=text,
            char_start=i * 200,
            char_end=(i + 1) * 200,
            token_count=len(text) // 4,
        )
        mock_db.add(chunk)
        chunks.append(chunk)

    mock_db.commit()
    return {"book": book, "section": section, "chunks": chunks}


@pytest.fixture
def sample_citations(sample_book):
    """Pre-built citation dicts for testing verification.

    Categories:
      - valid_exact:           exact substring match in the correct chunk
      - valid_fuzzy:           exact substring match (also qualifies as exact)
      - invalid_wrong_chunk:   text exists in the corpus but is cited against
                               the wrong chunk
      - invalid_hallucinated:  completely fabricated quote
      - invalid_missing_chunk: chunk_id does not exist in the database
    """
    chunks = sample_book["chunks"]
    return {
        "valid_exact": [
            {
                "chunk_id": chunks[0].id,
                "text": "The morning sun cast long shadows across the empty courtyard",
            },
            {
                "chunk_id": chunks[2].id,
                "text": "The river wound through the valley like a silver ribbon",
            },
        ],
        "valid_fuzzy": [
            {
                "chunk_id": chunks[1].id,
                "text": "The letter in his pocket felt heavier than any stone",
            },
        ],
        "invalid_wrong_chunk": [
            {
                "chunk_id": chunks[0].id,
                "text": "The river wound through the valley",
            },
        ],
        "invalid_hallucinated": [
            {
                "chunk_id": chunks[3].id,
                "text": "This text does not exist anywhere in the book at all",
            },
        ],
        "invalid_missing_chunk": [
            {
                "chunk_id": "nonexistent-id-12345",
                "text": "Some quoted text",
            },
        ],
    }


@pytest.fixture
def sample_session(mock_db, sample_book):
    """Create a discussion session for the sample book."""
    book = sample_book["book"]
    section = sample_book["section"]

    session = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="warmup",
        is_active=True,
    )
    mock_db.add(session)
    mock_db.commit()
    return session
