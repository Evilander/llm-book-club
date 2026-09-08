"""Tests for the SQLAlchemy ORM models.

Covers:
  - Model creation, relationships, and constraints
  - Enum types
  - Data integrity (required fields, defaults)
"""
import uuid

import pytest

from app.db.models import (
    Book,
    Section,
    Chunk,
    DiscussionSession,
    Message,
    IngestStatus,
    DiscussionMode,
    MessageRole,
)


# =========================================================================
# Enum types
# =========================================================================


class TestEnumTypes:
    """Verify enum values match expected constants."""

    def test_ingest_status_values(self):
        assert IngestStatus.QUEUED == "queued"
        assert IngestStatus.PROCESSING == "processing"
        assert IngestStatus.COMPLETED == "completed"
        assert IngestStatus.FAILED == "failed"

    def test_discussion_mode_values(self):
        assert DiscussionMode.GUIDED == "guided"
        assert DiscussionMode.SOCRATIC == "socratic"
        assert DiscussionMode.POETRY == "poetry"
        assert DiscussionMode.NONFICTION == "nonfiction"

    def test_message_role_values(self):
        assert MessageRole.USER == "user"
        assert MessageRole.FACILITATOR == "facilitator"
        assert MessageRole.CLOSE_READER == "close_reader"
        assert MessageRole.SKEPTIC == "skeptic"
        assert MessageRole.SYSTEM == "system"


# =========================================================================
# Book model
# =========================================================================


class TestBookModel:
    """Test Book creation and defaults."""

    def test_create_book(self, mock_db):
        book = Book(
            id=str(uuid.uuid4()),
            title="Test Book",
            author="Author",
            filename="test.pdf",
            file_type="pdf",
            file_size_bytes=5000,
        )
        mock_db.add(book)
        mock_db.commit()

        fetched = mock_db.query(Book).filter(Book.id == book.id).first()
        assert fetched is not None
        assert fetched.title == "Test Book"
        assert fetched.author == "Author"
        assert fetched.file_type == "pdf"

    def test_book_default_ingest_status(self, mock_db):
        book = Book(
            id=str(uuid.uuid4()),
            title="Defaults Test",
            filename="d.pdf",
            file_type="pdf",
            file_size_bytes=100,
        )
        mock_db.add(book)
        mock_db.commit()
        mock_db.refresh(book)
        assert book.ingest_status == IngestStatus.QUEUED

    def test_book_nullable_fields(self, mock_db):
        book = Book(
            id=str(uuid.uuid4()),
            title="Minimal",
            filename="m.pdf",
            file_type="pdf",
            file_size_bytes=100,
        )
        mock_db.add(book)
        mock_db.commit()
        mock_db.refresh(book)
        assert book.author is None
        assert book.total_chars is None
        assert book.cover_image_path is None


# =========================================================================
# Section model
# =========================================================================


class TestSectionModel:
    def test_create_section(self, mock_db, sample_book):
        sections = (
            mock_db.query(Section)
            .filter(Section.book_id == sample_book["book"].id)
            .all()
        )
        assert len(sections) == 1
        assert sections[0].title == "Chapter 1: The Beginning"
        assert sections[0].order_index == 0

    def test_section_book_relationship(self, mock_db, sample_book):
        section = sample_book["section"]
        mock_db.refresh(section)
        assert section.book_id == sample_book["book"].id


# =========================================================================
# Chunk model
# =========================================================================


class TestChunkModel:
    def test_chunks_created(self, mock_db, sample_book):
        chunks = (
            mock_db.query(Chunk)
            .filter(Chunk.book_id == sample_book["book"].id)
            .order_by(Chunk.order_index)
            .all()
        )
        assert len(chunks) == 5

    def test_chunk_ordering(self, mock_db, sample_book):
        chunks = (
            mock_db.query(Chunk)
            .filter(Chunk.section_id == sample_book["section"].id)
            .order_by(Chunk.order_index)
            .all()
        )
        for i, chunk in enumerate(chunks):
            assert chunk.order_index == i

    def test_chunk_text_not_empty(self, mock_db, sample_book):
        chunks = mock_db.query(Chunk).filter(
            Chunk.book_id == sample_book["book"].id
        ).all()
        for chunk in chunks:
            assert chunk.text is not None
            assert len(chunk.text) > 0

    def test_chunk_char_ranges(self, mock_db, sample_book):
        chunks = (
            mock_db.query(Chunk)
            .filter(Chunk.book_id == sample_book["book"].id)
            .order_by(Chunk.order_index)
            .all()
        )
        for chunk in chunks:
            assert chunk.char_end > chunk.char_start


# =========================================================================
# DiscussionSession model
# =========================================================================


class TestDiscussionSessionModel:
    def test_create_session(self, mock_db, sample_session):
        fetched = (
            mock_db.query(DiscussionSession)
            .filter(DiscussionSession.id == sample_session.id)
            .first()
        )
        assert fetched is not None
        assert fetched.mode == DiscussionMode.GUIDED
        assert fetched.is_active is True
        assert fetched.current_phase == "warmup"

    def test_session_section_ids(self, mock_db, sample_session, sample_book):
        assert sample_session.section_ids == [sample_book["section"].id]


# =========================================================================
# Message model
# =========================================================================


class TestMessageModel:
    def test_create_message(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.USER,
            content="What is the significance of the courtyard scene?",
        )
        mock_db.add(msg)
        mock_db.commit()

        fetched = mock_db.query(Message).filter(Message.id == msg.id).first()
        assert fetched is not None
        assert fetched.role == MessageRole.USER
        assert "courtyard" in fetched.content

    def test_message_with_citations(self, mock_db, sample_session, sample_book):
        chunk = sample_book["chunks"][0]
        citations = [
            {
                "chunk_id": chunk.id,
                "text": "The morning sun cast long shadows",
                "verified": True,
            }
        ]
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.FACILITATOR,
            content="The opening scene sets up the mood.",
            citations=citations,
        )
        mock_db.add(msg)
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.citations is not None
        assert len(msg.citations) == 1
        assert msg.citations[0]["chunk_id"] == chunk.id

    def test_message_nullable_citations(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.USER,
            content="Simple question.",
        )
        mock_db.add(msg)
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.citations is None

    def test_message_ordering(self, mock_db, sample_session):
        """Messages should be orderable by created_at."""
        import time

        msgs = []
        for i in range(3):
            msg = Message(
                id=str(uuid.uuid4()),
                session_id=sample_session.id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.FACILITATOR,
                content=f"Message {i}",
            )
            mock_db.add(msg)
            mock_db.commit()
            msgs.append(msg)

        fetched = (
            mock_db.query(Message)
            .filter(Message.session_id == sample_session.id)
            .order_by(Message.created_at)
            .all()
        )
        assert len(fetched) == 3
