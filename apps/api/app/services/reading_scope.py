"""A server-derived reading boundary, pinned for the duration of a turn."""
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, load_only

from ..db.models import Chunk, Message, Section
from ..settings import settings
from .reader_text import ReadingText, assemble_reading_text, page_bounds


class ReaderPosition(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(default=1800, ge=200, le=4000)
    edition_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def load_reading_chunks(db: Session, book_id: str) -> list[Chunk]:
    # Reading needs prose and coordinates, never thousands of embedding arrays.
    chunks = db.query(Chunk).options(load_only(
        Chunk.id, Chunk.section_id, Chunk.text, Chunk.char_start, Chunk.char_end,
        Chunk.order_index, Chunk.source_ref,
    )).join(Section, Section.id == Chunk.section_id).filter(
        Chunk.book_id == book_id, Section.book_id == book_id,
    ).order_by(Section.order_index, Chunk.order_index, Chunk.char_start, Chunk.id).all()
    return chunks


def load_reading(db: Session, book_id: str) -> tuple[ReadingText, list[Chunk]]:
    chunks = load_reading_chunks(db, book_id)
    return assemble_reading_text(chunks), chunks


@dataclass(frozen=True)
class ReadingScope:
    edition_id: str
    char_end: int
    book_length: int
    section_ids: list[str]
    spans: dict[str, tuple[int, int]]
    current_page_text: str | None = None
    position: dict | None = None
    initial_evidence: list[dict] = field(default_factory=list)

    @property
    def metadata(self) -> dict:
        return {"edition_id": self.edition_id, "char_end": self.char_end}

    @property
    def covers_book(self) -> bool:
        return self.char_end >= self.book_length > 0

    def filter_history(self, query):
        recorded = Message.metadata_json["reading_scope"]
        allowed = and_(
            recorded["edition_id"].as_string() == self.edition_id,
            recorded["char_end"].as_integer() <= self.char_end,
            recorded["char_end"].as_integer() > 0,
        )
        if self.covers_book:
            # Old turns have no trustworthy page provenance. Keep them saved;
            # they become available when there is no unread part of the book.
            allowed = or_(allowed, recorded["edition_id"].as_string().is_(None))
        return query.filter(allowed)


def build_scope(reading: ReadingText, *, position: ReaderPosition | None = None,
                section_ids: list[str] | None = None) -> ReadingScope:
    edition_id = reading.edition_id
    page_text = None
    page_start = 0
    saved_position = None
    if position is not None:
        if position.edition_id is not None and position.edition_id != edition_id:
            raise ValueError("This book has changed. Reopen the page before continuing.")
        if not reading.text or (position.page - 1) * position.page_size >= len(reading.text):
            raise ValueError("Reading page not found.")
        start, end = page_bounds(reading.text, position.page, position.page_size)
        page_start = start
        page_text = reading.text[start:end]
        saved_position = {**position.model_dump(), "edition_id": edition_id}
        eligible = [s for s in reading.chunks if s["char_start"] < end]
    else:
        selected = set(section_ids or [])
        eligible = [s for s in reading.chunks if s["section_id"] in selected]
        end = max((s["char_end"] for s in eligible), default=0)
    spans = {s["chunk_id"]: (0, min(s["char_end"], end) - s["char_start"]) for s in eligible}
    # Reserve half the evidence allowance for question-specific retrieval. A
    # normal reader page is smaller than this; long book-club slices may not be.
    remaining = settings.max_context_tokens * 2 if settings.max_context_tokens > 0 else sum(s["char_end"] - s["char_start"] for s in eligible)
    initial_evidence = []
    for span in eligible:
        start, stop = max(span["char_start"], page_start), min(span["char_end"], end)
        if start < stop and remaining > 0:
            text = reading.text[start:stop][:remaining]
            initial_evidence.append({"chunk_id": span["chunk_id"], "text": text})
            remaining -= len(text)
    return ReadingScope(
        edition_id=edition_id, char_end=end, book_length=len(reading.text),
        section_ids=list(dict.fromkeys(s["section_id"] for s in eligible)),
        spans=spans, current_page_text=page_text, position=saved_position,
        initial_evidence=initial_evidence,
    )


def session_scope(db: Session, session, position: ReaderPosition | None = None) -> ReadingScope:
    preferences = session.preferences_json or {}
    if preferences.get("reading_companion"):
        saved = preferences.get("reading_position")
        if position is None:
            if not saved:
                raise ValueError("Open the current page with your companion before continuing.")
            position = ReaderPosition.model_validate(saved)
    elif position is not None:
        raise ValueError("A page position belongs to a reading companion session.")
    reading, _chunks = load_reading(db, session.book_id)
    return build_scope(reading, position=position, section_ids=session.section_ids)
