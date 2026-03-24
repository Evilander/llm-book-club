"""Memory and progress endpoints aligned to the current ORM schema."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import (
    AchievementType,
    BookMemory,
    Connection,
    KeyMoment,
    NoteType,
    ReadingUnit,
    ReadingUnitStatus,
    TrackedCharacter,
    TrackedTheme,
    UserNote,
    get_db,
)

router = APIRouter(prefix="/v1/memory", tags=["memory"])


class ReadingUnitResponse(BaseModel):
    id: str
    title: str
    unit_type: str
    order_index: int
    estimated_tokens: int | None = None
    estimated_reading_min: int | None = None
    status: str
    narrative_thread: str | None = None
    summary: str | None = None


class BookMemoryResponse(BaseModel):
    book_id: str
    current_unit_id: str | None = None
    units_completed: list[str]
    total_reading_time_min: int
    xp_earned: int
    achievements_unlocked: list[str]
    reading_progress_pct: float


class ProgressUpdate(BaseModel):
    status: str
    time_spent_min: int | None = None


class KeyMomentCreate(BaseModel):
    reading_unit_id: str | None = None
    chunk_id: str | None = None
    title: str
    description: str
    quote: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    significance: str | None = None
    moment_type: str = "plot"
    source: str = "user"


class KeyMomentResponse(BaseModel):
    id: str
    reading_unit_id: str | None = None
    chunk_id: str | None = None
    title: str
    description: str
    quote: str | None = None
    significance: str | None = None
    moment_type: str
    source: str
    created_at: datetime


class ThemeCreate(BaseModel):
    name: str
    description: str | None = None
    first_seen_unit_id: str | None = None
    source: str = "user"


class ThemeResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    evidence_count: int
    strength: float
    first_seen_unit_id: str | None = None
    source: str


class CharacterCreate(BaseModel):
    name: str
    description: str | None = None
    first_appearance_unit_id: str | None = None


class CharacterResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    aliases: list[str] | None = None
    arc_notes: list[dict]
    first_appearance_unit_id: str | None = None
    prominence: float


class UserNoteCreate(BaseModel):
    reading_unit_id: str | None = None
    chunk_id: str | None = None
    content: str
    note_type: str = "note"
    highlighted_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    tags: list[str] | None = None


class UserNoteResponse(BaseModel):
    id: str
    content: str
    note_type: str
    reading_unit_id: str | None = None
    chunk_id: str | None = None
    highlighted_text: str | None = None
    created_at: datetime


class ConnectionCreate(BaseModel):
    from_unit_id: str
    to_unit_id: str
    from_quote: str | None = None
    to_quote: str | None = None
    connection_type: str
    explanation: str
    source: str = "user"


def _get_memory_or_404(db: Session, book_id: str) -> BookMemory:
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
      raise HTTPException(status_code=404, detail="Book memory not found")
    return memory


def _unit_status(memory: BookMemory, unit_id: str) -> ReadingUnitStatus:
    if unit_id in (memory.units_completed or []):
        return ReadingUnitStatus.COMPLETED
    if memory.current_unit_id == unit_id:
        return ReadingUnitStatus.IN_PROGRESS
    return ReadingUnitStatus.UNREAD


def _award_progress_xp(unit: ReadingUnit) -> int:
    return 50 + min(50, (unit.estimated_reading_min or 10) * 2)


@router.get("/books/{book_id}/units", response_model=list[ReadingUnitResponse])
async def get_reading_units(book_id: str, status: str | None = None, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    units = (
        db.query(ReadingUnit)
        .filter(ReadingUnit.book_id == book_id)
        .order_by(ReadingUnit.order_index)
        .all()
    )

    filtered: list[ReadingUnitResponse] = []
    for unit in units:
        derived_status = _unit_status(memory, unit.id).value
        if status and derived_status != status:
            continue
        filtered.append(
            ReadingUnitResponse(
                id=unit.id,
                title=unit.title,
                unit_type=unit.unit_type.value if hasattr(unit.unit_type, "value") else str(unit.unit_type),
                order_index=unit.order_index,
                estimated_tokens=unit.estimated_tokens,
                estimated_reading_min=unit.estimated_reading_min,
                status=derived_status,
                narrative_thread=unit.narrative_thread,
                summary=unit.summary,
            )
        )
    return filtered


@router.get("/books/{book_id}", response_model=BookMemoryResponse)
async def get_book_memory(book_id: str, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    total_units = db.query(ReadingUnit).filter(ReadingUnit.book_id == book_id).count()
    completed_count = len(memory.units_completed or [])
    return BookMemoryResponse(
        book_id=book_id,
        current_unit_id=memory.current_unit_id,
        units_completed=memory.units_completed or [],
        total_reading_time_min=memory.total_reading_time_min or 0,
        xp_earned=memory.xp_earned or 0,
        achievements_unlocked=memory.achievements_unlocked or [],
        reading_progress_pct=(completed_count / total_units * 100) if total_units > 0 else 0,
    )


@router.post("/books/{book_id}/units/{unit_id}/progress")
async def update_unit_progress(
    book_id: str,
    unit_id: str,
    update: ProgressUpdate,
    db: Session = Depends(get_db),
):
    memory = _get_memory_or_404(db, book_id)
    unit = (
        db.query(ReadingUnit)
        .filter(ReadingUnit.book_id == book_id, ReadingUnit.id == unit_id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Reading unit not found")

    try:
        status = ReadingUnitStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    xp_earned = 0
    completed = list(memory.units_completed or [])
    if status == ReadingUnitStatus.COMPLETED and unit_id not in completed:
        completed.append(unit_id)
        memory.units_completed = completed
        memory.current_unit_id = unit_id
        xp_earned = _award_progress_xp(unit)
        memory.xp_earned = (memory.xp_earned or 0) + xp_earned
    elif status == ReadingUnitStatus.IN_PROGRESS:
        memory.current_unit_id = unit_id
    elif status == ReadingUnitStatus.UNREAD:
        memory.current_unit_id = None if memory.current_unit_id == unit_id else memory.current_unit_id
        memory.units_completed = [value for value in completed if value != unit_id]

    if update.time_spent_min:
        memory.total_reading_time_min = (memory.total_reading_time_min or 0) + update.time_spent_min

    memory.last_read_at = datetime.utcnow()
    db.commit()
    return {"status": status.value, "xp_earned": xp_earned}


@router.get("/books/{book_id}/moments", response_model=list[KeyMomentResponse])
async def get_key_moments(
    book_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    memory = _get_memory_or_404(db, book_id)
    moments = (
        db.query(KeyMoment)
        .filter(KeyMoment.book_memory_id == memory.id)
        .order_by(KeyMoment.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        KeyMomentResponse(
            id=moment.id,
            reading_unit_id=moment.reading_unit_id,
            chunk_id=moment.chunk_id,
            title=moment.title,
            description=moment.description,
            quote=moment.quote,
            significance=moment.significance,
            moment_type=moment.moment_type,
            source=moment.source,
            created_at=moment.created_at,
        )
        for moment in moments
    ]


@router.post("/books/{book_id}/moments", response_model=KeyMomentResponse)
async def create_key_moment(book_id: str, moment: KeyMomentCreate, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    new_moment = KeyMoment(
        book_memory_id=memory.id,
        reading_unit_id=moment.reading_unit_id,
        chunk_id=moment.chunk_id,
        title=moment.title,
        description=moment.description,
        quote=moment.quote,
        char_start=moment.char_start,
        char_end=moment.char_end,
        significance=moment.significance,
        moment_type=moment.moment_type,
        source=moment.source,
    )
    db.add(new_moment)
    memory.xp_earned = (memory.xp_earned or 0) + 5
    db.commit()
    db.refresh(new_moment)
    return KeyMomentResponse(
        id=new_moment.id,
        reading_unit_id=new_moment.reading_unit_id,
        chunk_id=new_moment.chunk_id,
        title=new_moment.title,
        description=new_moment.description,
        quote=new_moment.quote,
        significance=new_moment.significance,
        moment_type=new_moment.moment_type,
        source=new_moment.source,
        created_at=new_moment.created_at,
    )


@router.get("/books/{book_id}/themes", response_model=list[ThemeResponse])
async def get_tracked_themes(book_id: str, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    themes = (
        db.query(TrackedTheme)
        .filter(TrackedTheme.book_memory_id == memory.id)
        .order_by(TrackedTheme.updated_at.desc())
        .all()
    )
    return [
        ThemeResponse(
            id=theme.id,
            name=theme.name,
            description=theme.description,
            evidence_count=len(theme.evidence or []),
            strength=theme.strength,
            first_seen_unit_id=theme.first_seen_unit_id,
            source=theme.source,
        )
        for theme in themes
    ]


@router.post("/books/{book_id}/themes", response_model=ThemeResponse)
async def create_tracked_theme(book_id: str, theme: ThemeCreate, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    new_theme = TrackedTheme(
        book_memory_id=memory.id,
        name=theme.name,
        description=theme.description,
        first_seen_unit_id=theme.first_seen_unit_id,
        source=theme.source,
        evidence=[],
    )
    db.add(new_theme)
    db.commit()
    db.refresh(new_theme)
    return ThemeResponse(
        id=new_theme.id,
        name=new_theme.name,
        description=new_theme.description,
        evidence_count=0,
        strength=new_theme.strength,
        first_seen_unit_id=new_theme.first_seen_unit_id,
        source=new_theme.source,
    )


@router.get("/books/{book_id}/characters", response_model=list[CharacterResponse])
async def get_tracked_characters(book_id: str, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    characters = (
        db.query(TrackedCharacter)
        .filter(TrackedCharacter.book_memory_id == memory.id)
        .order_by(TrackedCharacter.updated_at.desc())
        .all()
    )
    return [
        CharacterResponse(
            id=character.id,
            name=character.name,
            description=character.description,
            aliases=character.aliases,
            arc_notes=character.arc_notes or [],
            first_appearance_unit_id=character.first_appearance_unit_id,
            prominence=character.prominence,
        )
        for character in characters
    ]


@router.post("/books/{book_id}/characters", response_model=CharacterResponse)
async def create_tracked_character(book_id: str, character: CharacterCreate, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    new_character = TrackedCharacter(
        book_memory_id=memory.id,
        name=character.name,
        description=character.description,
        first_appearance_unit_id=character.first_appearance_unit_id,
        arc_notes=[],
    )
    db.add(new_character)
    db.commit()
    db.refresh(new_character)
    return CharacterResponse(
        id=new_character.id,
        name=new_character.name,
        description=new_character.description,
        aliases=new_character.aliases,
        arc_notes=new_character.arc_notes or [],
        first_appearance_unit_id=new_character.first_appearance_unit_id,
        prominence=new_character.prominence,
    )


@router.get("/books/{book_id}/notes", response_model=list[UserNoteResponse])
async def get_user_notes(
    book_id: str,
    unit_id: str | None = None,
    note_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    memory = _get_memory_or_404(db, book_id)
    query = db.query(UserNote).filter(UserNote.book_memory_id == memory.id)
    if unit_id:
        query = query.filter(UserNote.reading_unit_id == unit_id)
    if note_type:
        try:
            parsed = NoteType(note_type)
            query = query.filter(UserNote.note_type == parsed)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid note_type: {note_type}")

    notes = query.order_by(UserNote.created_at.desc()).limit(limit).all()
    return [
        UserNoteResponse(
            id=note.id,
            content=note.content,
            note_type=note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type),
            reading_unit_id=note.reading_unit_id,
            chunk_id=note.chunk_id,
            highlighted_text=note.highlighted_text,
            created_at=note.created_at,
        )
        for note in notes
    ]


@router.post("/books/{book_id}/notes", response_model=UserNoteResponse)
async def create_user_note(book_id: str, note: UserNoteCreate, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    try:
        parsed_type = NoteType(note.note_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid note_type: {note.note_type}")

    new_note = UserNote(
        book_memory_id=memory.id,
        reading_unit_id=note.reading_unit_id,
        chunk_id=note.chunk_id,
        content=note.content,
        note_type=parsed_type,
        highlighted_text=note.highlighted_text,
        char_start=note.char_start,
        char_end=note.char_end,
        tags=note.tags,
    )
    db.add(new_note)

    xp_awards = {
        NoteType.HIGHLIGHT: 2,
        NoteType.NOTE: 5,
        NoteType.QUESTION: 5,
        NoteType.INSIGHT: 10,
        NoteType.CONNECTION: 15,
    }
    memory.xp_earned = (memory.xp_earned or 0) + xp_awards.get(parsed_type, 5)

    if parsed_type == NoteType.INSIGHT and AchievementType.FIRST_INSIGHT.value not in (memory.achievements_unlocked or []):
        achievements = list(memory.achievements_unlocked or [])
        achievements.append(AchievementType.FIRST_INSIGHT.value)
        memory.achievements_unlocked = achievements
        memory.xp_earned += 50

    db.commit()
    db.refresh(new_note)
    return UserNoteResponse(
        id=new_note.id,
        content=new_note.content,
        note_type=new_note.note_type.value if hasattr(new_note.note_type, "value") else str(new_note.note_type),
        reading_unit_id=new_note.reading_unit_id,
        chunk_id=new_note.chunk_id,
        highlighted_text=new_note.highlighted_text,
        created_at=new_note.created_at,
    )


@router.post("/books/{book_id}/connections")
async def create_connection(book_id: str, connection: ConnectionCreate, db: Session = Depends(get_db)):
    memory = _get_memory_or_404(db, book_id)
    new_connection = Connection(
        book_memory_id=memory.id,
        from_unit_id=connection.from_unit_id,
        to_unit_id=connection.to_unit_id,
        from_quote=connection.from_quote,
        to_quote=connection.to_quote,
        connection_type=connection.connection_type,
        explanation=connection.explanation,
        source=connection.source,
    )
    db.add(new_connection)
    memory.xp_earned = (memory.xp_earned or 0) + 20
    db.commit()
    db.refresh(new_connection)
    return {"status": "created", "id": new_connection.id}
