from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    Enum,
    Index,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class IngestStatus(str, PyEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscussionMode(str, PyEnum):
    # New warm modes (primary)
    CONVERSATION = "conversation"
    FIRST_TIME = "first_time"
    DEEP_DIVE = "deep_dive"
    BIG_PICTURE = "big_picture"
    # Legacy modes (backward compat)
    GUIDED = "guided"
    SOCRATIC = "socratic"
    POETRY = "poetry"
    NONFICTION = "nonfiction"


class MessageRole(str, PyEnum):
    USER = "user"
    FACILITATOR = "facilitator"
    CLOSE_READER = "close_reader"
    SKEPTIC = "skeptic"
    AFTER_DARK_GUIDE = "after_dark_guide"
    SYSTEM = "system"


class ReadingUnitType(str, PyEnum):
    CHAPTER = "chapter"
    SECTION = "section"
    PART = "part"
    SCENE = "scene"
    ENDNOTE_BATCH = "endnote_batch"
    PROLOGUE = "prologue"
    EPILOGUE = "epilogue"
    INTERLUDE = "interlude"


class ReadingUnitStatus(str, PyEnum):
    UNREAD = "unread"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class NoteType(str, PyEnum):
    HIGHLIGHT = "highlight"
    NOTE = "note"
    QUESTION = "question"
    INSIGHT = "insight"
    CONNECTION = "connection"


class AchievementType(str, PyEnum):
    FIRST_INSIGHT = "first_insight"
    BOOKWORM_7 = "bookworm_7"
    BOOKWORM_30 = "bookworm_30"
    CLOSE_READER = "close_reader"
    THEME_HUNTER = "theme_hunter"
    SOCRATIC_SCHOLAR = "socratic_scholar"
    COMPLETIONIST = "completionist"
    QUIZ_MASTER = "quiz_master"
    CONNECTION_KING = "connection_king"
    FIRST_BOOK = "first_book"
    FIVE_BOOKS = "five_books"
    MARATHON_SESSION = "marathon_session"


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Book(Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf or epub
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus), default=IngestStatus.QUEUED
    )
    ingest_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    cover_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    sections: Mapped[list["Section"]] = relationship(
        "Section", back_populates="book", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["DiscussionSession"]] = relationship(
        "DiscussionSession", back_populates="book", cascade="all, delete-orphan"
    )


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    section_type: Mapped[str] = mapped_column(String(50), nullable=False)  # chapter, poem, essay, etc.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)

    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)  # for PDFs
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    token_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reading_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    book: Mapped["Book"] = relationship("Book", back_populates="sections")
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="section", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_sections_book_order", "book_id", "order_index"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)

    # Source reference (page number for PDF, location for EPUB)
    source_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # pgvector embedding (1536 for text-embedding-3-small, 3072 for large)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(3072), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    section: Mapped["Section"] = relationship("Section", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_book_section", "book_id", "section_id"),
        Index("ix_chunks_section_order", "section_id", "order_index"),
        # HNSW index on embedding is created via Alembic migration (001) using raw SQL:
        #   CREATE INDEX ix_chunks_embedding_hnsw ON chunks
        #   USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
        # A generated tsvector column (text_search) and GIN index are also managed there.
    )


class DiscussionSession(Base):
    __tablename__ = "discussion_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )

    mode: Mapped[DiscussionMode] = mapped_column(
        Enum(DiscussionMode), default=DiscussionMode.GUIDED
    )
    time_budget_min: Mapped[int] = mapped_column(Integer, default=20)

    # JSON array of section IDs in this session
    section_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    # Current discussion state
    current_phase: Mapped[str] = mapped_column(String(50), default="warmup")
    is_active: Mapped[bool] = mapped_column(default=True)
    preferences_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Summary and notes
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    book: Mapped["Book"] = relationship("Book", back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_sessions_book_active", "book_id", "is_active"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discussion_sessions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Citations: JSON array of {chunk_id, char_start, char_end, text_snippet}
    citations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    # Audio file path if TTS was generated
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Extensible metadata (token counts, latency, model, citation verification, etc.)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # User feedback: "up", "down", or null
    feedback: Mapped[str | None] = mapped_column(String(10), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["DiscussionSession"] = relationship("DiscussionSession", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
    )


# =============================================================================
# READING UNITS - Intelligent chunking for massive texts
# =============================================================================

class ReadingUnit(Base):
    """
    A digestible reading unit - replaces simple chapter concept.
    Created by intelligent chunking that respects narrative boundaries.
    """
    __tablename__ = "reading_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )

    # Identity
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    unit_type: Mapped[ReadingUnitType] = mapped_column(
        Enum(ReadingUnitType), default=ReadingUnitType.CHAPTER
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Boundaries in source text
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_refs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ["pp. 1-20", "endnotes 1-5"]

    # Metadata
    estimated_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_reading_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    characters_present: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    themes_touched: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # For non-linear narratives (e.g., Infinite Jest timeline)
    chronological_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    narrative_thread: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "Hal", "Gately", etc.

    # Relationships between units
    related_unit_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    prerequisite_unit_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # AI-generated summary (created after user completes unit)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_quotes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_reading_units_book_order", "book_id", "order_index"),
        Index("ix_reading_units_book_thread", "book_id", "narrative_thread"),
    )


# =============================================================================
# BOOK MEMORY - Persistent memory that grows as user reads
# =============================================================================

class BookMemory(Base):
    """
    Persistent memory for a user's journey through a book.
    This is the core state that agents reference.
    """
    __tablename__ = "book_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    # user_id will be added when auth is implemented
    # user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    # Progress tracking
    current_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    units_completed: Mapped[list[str]] = mapped_column(JSON, default=list)
    total_reading_time_min: Mapped[int] = mapped_column(Integer, default=0)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reading preferences for this book
    preferred_session_length_min: Mapped[int] = mapped_column(Integer, default=30)
    complexity_adjustment: Mapped[float] = mapped_column(Float, default=1.0)  # 0.5-1.5

    # Comprehension tracking
    avg_quiz_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_quizzes_taken: Mapped[int] = mapped_column(Integer, default=0)
    strengths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ["character analysis", "theme identification"]
    areas_to_revisit: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Gamification
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    achievements_unlocked: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Book-specific insights the AI has generated
    ai_observations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    key_moments: Mapped[list["KeyMoment"]] = relationship(
        "KeyMoment", back_populates="book_memory", cascade="all, delete-orphan"
    )
    themes: Mapped[list["TrackedTheme"]] = relationship(
        "TrackedTheme", back_populates="book_memory", cascade="all, delete-orphan"
    )
    characters: Mapped[list["TrackedCharacter"]] = relationship(
        "TrackedCharacter", back_populates="book_memory", cascade="all, delete-orphan"
    )
    user_notes: Mapped[list["UserNote"]] = relationship(
        "UserNote", back_populates="book_memory", cascade="all, delete-orphan"
    )
    quiz_results: Mapped[list["QuizResult"]] = relationship(
        "QuizResult", back_populates="book_memory", cascade="all, delete-orphan"
    )
    connections: Mapped[list["Connection"]] = relationship(
        "Connection", back_populates="book_memory", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_book_memories_book", "book_id"),
        # Index("ix_book_memories_user_book", "user_id", "book_id"),  # Enable with auth
    )


class KeyMoment(Base):
    """
    A pivotal moment in the book that the user or AI identified as significant.
    """
    __tablename__ = "key_moments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("book_memories.id", ondelete="CASCADE"), nullable=False
    )
    reading_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # The moment
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Why it matters
    significance: Mapped[str | None] = mapped_column(Text, nullable=True)
    moment_type: Mapped[str] = mapped_column(String(50), default="plot")  # plot, character, theme, symbol, foreshadowing

    # Who identified it
    source: Mapped[str] = mapped_column(String(20), default="user")  # user, ai, discussion

    # Connections to other moments (stored as list of moment IDs)
    connected_moment_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    book_memory: Mapped["BookMemory"] = relationship("BookMemory", back_populates="key_moments")

    __table_args__ = (
        Index("ix_key_moments_memory", "book_memory_id"),
    )


class TrackedTheme(Base):
    """
    A theme identified and tracked through the book.
    """
    __tablename__ = "tracked_themes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("book_memories.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Evidence: list of {unit_id, quote, explanation}
    evidence: Mapped[list[dict]] = mapped_column(JSON, default=list)

    # How prominent is this theme (0.0-1.0)
    strength: Mapped[float] = mapped_column(Float, default=0.5)

    # Who identified it
    source: Mapped[str] = mapped_column(String(20), default="ai")  # user, ai, discussion

    # First appearance
    first_seen_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    book_memory: Mapped["BookMemory"] = relationship("BookMemory", back_populates="themes")


class TrackedCharacter(Base):
    """
    A character tracked through the book with their arc and relationships.
    """
    __tablename__ = "tracked_characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("book_memories.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Description that evolves
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_impression: Mapped[str | None] = mapped_column(Text, nullable=True)  # User's first take
    current_impression: Mapped[str | None] = mapped_column(Text, nullable=True)  # How they see them now

    # First and notable appearances
    first_appearance_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notable_moments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # KeyMoment IDs

    # Relationships: {character_name: relationship_description}
    relationships: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Character arc notes: [{unit_id, observation}]
    arc_notes: Mapped[list[dict]] = mapped_column(JSON, default=list)

    # How important to the story (0.0-1.0)
    prominence: Mapped[float] = mapped_column(Float, default=0.5)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    book_memory: Mapped["BookMemory"] = relationship("BookMemory", back_populates="characters")


class UserNote(Base):
    """
    User's highlights, notes, questions, and insights.
    """
    __tablename__ = "user_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("book_memories.id", ondelete="CASCADE"), nullable=False
    )
    reading_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    note_type: Mapped[NoteType] = mapped_column(Enum(NoteType), default=NoteType.NOTE)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # For highlights, the exact text
    highlighted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # AI response to user's note (if they asked a question or made an insight)
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tags for organization
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    book_memory: Mapped["BookMemory"] = relationship("BookMemory", back_populates="user_notes")

    __table_args__ = (
        Index("ix_user_notes_memory", "book_memory_id"),
        Index("ix_user_notes_unit", "reading_unit_id"),
    )


class Connection(Base):
    """
    A connection between two parts of the book - cross-references, callbacks, parallels.
    """
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("book_memories.id", ondelete="CASCADE"), nullable=False
    )

    # The two points being connected
    from_unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_unit_id: Mapped[str] = mapped_column(String(36), nullable=False)
    from_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The connection
    connection_type: Mapped[str] = mapped_column(String(50), nullable=False)  # parallel, callback, foreshadowing, contrast, thematic
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    # Who found it
    source: Mapped[str] = mapped_column(String(20), default="ai")  # user, ai
    user_validated: Mapped[bool] = mapped_column(default=False)  # User confirmed AI's connection

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    book_memory: Mapped["BookMemory"] = relationship("BookMemory", back_populates="connections")

    __table_args__ = (
        Index("ix_connections_memory", "book_memory_id"),
    )


class QuizResult(Base):
    """
    Results from a comprehension quiz.
    """
    __tablename__ = "quiz_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    book_memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("book_memories.id", ondelete="CASCADE"), nullable=False
    )
    reading_unit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Quiz content
    questions: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    # Each question: {question, type, options?, correct_answer, user_answer, correct}

    # Results
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    questions_total: Mapped[int] = mapped_column(Integer, nullable=False)
    questions_correct: Mapped[int] = mapped_column(Integer, nullable=False)

    # Gamification
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")  # easy, medium, hard

    # Time taken
    time_taken_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    book_memory: Mapped["BookMemory"] = relationship("BookMemory", back_populates="quiz_results")

    __table_args__ = (
        Index("ix_quiz_results_memory", "book_memory_id"),
    )


# =============================================================================
# USER PROGRESS - Global gamification state
# =============================================================================

class UserProgress(Base):
    """
    Global user progress across all books.
    (Will be linked to User model when auth is added)
    """
    __tablename__ = "user_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    # user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True)

    # XP and Level
    total_xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    level_name: Mapped[str] = mapped_column(String(50), default="Novice Reader")

    # Streaks
    current_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Global stats
    books_started: Mapped[int] = mapped_column(Integer, default=0)
    books_completed: Mapped[int] = mapped_column(Integer, default=0)
    total_reading_time_min: Mapped[int] = mapped_column(Integer, default=0)
    total_quizzes_taken: Mapped[int] = mapped_column(Integer, default=0)
    total_notes_created: Mapped[int] = mapped_column(Integer, default=0)
    total_connections_found: Mapped[int] = mapped_column(Integer, default=0)

    # Achievements: list of {achievement_type, unlocked_at, book_id?}
    achievements: Mapped[list[dict]] = mapped_column(JSON, default=list)

    # Preferences
    preferred_discussion_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_session_length_min: Mapped[int] = mapped_column(Integer, default=30)
    voice_enabled: Mapped[bool] = mapped_column(default=False)
    quiz_difficulty_preference: Mapped[str] = mapped_column(String(20), default="adaptive")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DailyActivity(Base):
    """
    Track daily reading activity for streaks and analytics.
    """
    __tablename__ = "daily_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_progress_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_progress.id", ondelete="CASCADE"), nullable=False
    )

    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reading_time_min: Mapped[int] = mapped_column(Integer, default=0)
    units_completed: Mapped[int] = mapped_column(Integer, default=0)
    quizzes_taken: Mapped[int] = mapped_column(Integer, default=0)
    notes_created: Mapped[int] = mapped_column(Integer, default=0)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0)

    # Which books were read
    books_read: Mapped[list[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_daily_activities_user_date", "user_progress_id", "date"),
    )
