"""
Memory and Progress API Endpoints

Endpoints for:
- Book memory (key moments, themes, characters, notes)
- Reading progress and units
- Connections and cross-chapter insights
"""

from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.engine import get_db
from ..db.models import (
    Book, BookMemory, ReadingUnit, ReadingUnitStatus,
    KeyMoment, TrackedTheme, TrackedCharacter, UserNote,
    NoteType, Connection, DailyActivity, AchievementType,
)
from ..discussion.memory_prompts import build_memory_from_db, MemoryContext

router = APIRouter(prefix="/v1/memory", tags=["memory"])


# =============================================================================
# SCHEMAS
# =============================================================================

class ReadingUnitResponse(BaseModel):
    id: str
    title: str
    unit_type: str
    order_index: int
    token_estimate: int
    reading_time_min: int
    status: str
    narrative_thread: Optional[str] = None
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class BookMemoryResponse(BaseModel):
    book_id: str
    current_unit_id: Optional[str] = None
    units_completed: list[str]
    total_reading_time_min: int
    xp_earned: int
    achievements_unlocked: list[str]
    reading_progress_pct: float


class KeyMomentCreate(BaseModel):
    reading_unit_id: str
    quote_text: str
    char_start: int
    char_end: int
    significance: Optional[str] = None


class KeyMomentResponse(BaseModel):
    id: str
    reading_unit_id: str
    quote_text: str
    significance: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ThemeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    first_appearance_unit_id: Optional[str] = None


class ThemeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    mention_count: int
    first_appearance_unit_id: Optional[str] = None

    class Config:
        from_attributes = True


class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    first_appearance_unit_id: Optional[str] = None


class CharacterResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    arc_notes: Optional[str] = None
    first_appearance_unit_id: Optional[str] = None

    class Config:
        from_attributes = True


class UserNoteCreate(BaseModel):
    reading_unit_id: str
    content: str
    note_type: str = "note"  # highlight, note, question, insight, connection
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class UserNoteResponse(BaseModel):
    id: str
    content: str
    note_type: str
    reading_unit_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConnectionCreate(BaseModel):
    source_unit_id: str
    source_char_start: int
    source_char_end: int
    source_description: str
    target_unit_id: str
    target_char_start: int
    target_char_end: int
    target_description: str
    connection_type: str  # echo, contrast, foreshadowing, callback, parallel, evolution


class ProgressUpdate(BaseModel):
    unit_id: str
    status: str  # unread, in_progress, completed
    time_spent_min: Optional[int] = None



# =============================================================================
# READING UNITS ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}/units", response_model=list[ReadingUnitResponse])
async def get_reading_units(
    book_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all reading units for a book."""
    query = db.query(ReadingUnit).filter(ReadingUnit.book_id == book_id)

    if status:
        try:
            status_enum = ReadingUnitStatus(status)
            query = query.filter(ReadingUnit.status == status_enum)
        except ValueError:
            pass

    units = query.order_by(ReadingUnit.order_index).all()
    return units


@router.get("/books/{book_id}/units/{unit_id}", response_model=ReadingUnitResponse)
async def get_reading_unit(
    book_id: str,
    unit_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific reading unit."""
    unit = db.query(ReadingUnit).filter(
        ReadingUnit.id == unit_id,
        ReadingUnit.book_id == book_id,
    ).first()

    if not unit:
        raise HTTPException(status_code=404, detail="Reading unit not found")

    return unit


@router.post("/books/{book_id}/units/{unit_id}/progress")
async def update_unit_progress(
    book_id: str,
    unit_id: str,
    update: ProgressUpdate,
    db: Session = Depends(get_db),
):
    """Update reading progress for a unit."""
    unit = db.query(ReadingUnit).filter(
        ReadingUnit.id == unit_id,
        ReadingUnit.book_id == book_id,
    ).first()

    if not unit:
        raise HTTPException(status_code=404, detail="Reading unit not found")

    # Update status
    try:
        unit.status = ReadingUnitStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    # Update BookMemory
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if memory:
        if update.status == "completed":
            if unit_id not in (memory.units_completed or []):
                completed = list(memory.units_completed or [])
                completed.append(unit_id)
                memory.units_completed = completed

                # Award XP for completing unit
                xp_reward = _calculate_unit_xp(unit)
                memory.xp_earned = (memory.xp_earned or 0) + xp_reward

        if update.status == "in_progress":
            memory.current_unit_id = unit_id

        if update.time_spent_min:
            memory.total_reading_time_min = (memory.total_reading_time_min or 0) + update.time_spent_min

    db.commit()

    # Update daily activity
    await _update_daily_activity(db, book_id, update.time_spent_min or 0)

    return {
        "status": "updated",
        "xp_earned": xp_reward if update.status == "completed" else 0,
    }


def _calculate_unit_xp(unit: ReadingUnit) -> int:
    """Calculate XP for completing a reading unit."""
    base_xp = 50
    # Bonus for longer units
    time_bonus = min(50, (unit.reading_time_min or 10) * 2)
    return base_xp + time_bonus


async def _update_daily_activity(db: Session, book_id: str, time_min: int):
    """Update daily reading activity for streak tracking."""
    today = date.today()
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        return

    activity = db.query(DailyActivity).filter(
        DailyActivity.memory_id == memory.id,
        DailyActivity.date == today,
    ).first()

    if activity:
        activity.reading_time_min += time_min
        activity.units_completed += 1
    else:
        activity = DailyActivity(
            memory_id=memory.id,
            date=today,
            reading_time_min=time_min,
            units_completed=1,
            xp_earned=0,
        )
        db.add(activity)

    db.commit()


# =============================================================================
# BOOK MEMORY ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}", response_model=BookMemoryResponse)
async def get_book_memory(
    book_id: str,
    db: Session = Depends(get_db),
):
    """Get the complete memory state for a book."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()

    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

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


# =============================================================================
# KEY MOMENTS ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}/moments", response_model=list[KeyMomentResponse])
async def get_key_moments(
    book_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get all key moments marked for a book."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    moments = db.query(KeyMoment).filter(
        KeyMoment.memory_id == memory.id
    ).order_by(KeyMoment.created_at.desc()).limit(limit).all()

    return moments


@router.post("/books/{book_id}/moments", response_model=KeyMomentResponse)
async def create_key_moment(
    book_id: str,
    moment: KeyMomentCreate,
    db: Session = Depends(get_db),
):
    """Mark a key moment in the text."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    new_moment = KeyMoment(
        memory_id=memory.id,
        reading_unit_id=moment.reading_unit_id,
        quote_text=moment.quote_text,
        char_start=moment.char_start,
        char_end=moment.char_end,
        significance=moment.significance,
    )
    db.add(new_moment)

    # Award XP for marking a moment
    memory.xp_earned = (memory.xp_earned or 0) + 5

    db.commit()
    db.refresh(new_moment)

    return new_moment


# =============================================================================
# THEMES ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}/themes", response_model=list[ThemeResponse])
async def get_tracked_themes(
    book_id: str,
    db: Session = Depends(get_db),
):
    """Get all tracked themes for a book."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    themes = db.query(TrackedTheme).filter(
        TrackedTheme.memory_id == memory.id
    ).order_by(TrackedTheme.mention_count.desc()).all()

    return themes


@router.post("/books/{book_id}/themes", response_model=ThemeResponse)
async def create_tracked_theme(
    book_id: str,
    theme: ThemeCreate,
    db: Session = Depends(get_db),
):
    """Start tracking a theme."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    new_theme = TrackedTheme(
        memory_id=memory.id,
        name=theme.name,
        description=theme.description,
        first_appearance_unit_id=theme.first_appearance_unit_id,
        mention_count=1,
    )
    db.add(new_theme)
    db.commit()
    db.refresh(new_theme)

    return new_theme


@router.post("/books/{book_id}/themes/{theme_id}/mention")
async def increment_theme_mention(
    book_id: str,
    theme_id: str,
    db: Session = Depends(get_db),
):
    """Increment the mention count for a theme."""
    theme = db.query(TrackedTheme).filter(TrackedTheme.id == theme_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    theme.mention_count = (theme.mention_count or 0) + 1
    db.commit()

    return {"status": "updated", "mention_count": theme.mention_count}


# =============================================================================
# CHARACTERS ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}/characters", response_model=list[CharacterResponse])
async def get_tracked_characters(
    book_id: str,
    db: Session = Depends(get_db),
):
    """Get all tracked characters for a book."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    characters = db.query(TrackedCharacter).filter(
        TrackedCharacter.memory_id == memory.id
    ).all()

    return characters


@router.post("/books/{book_id}/characters", response_model=CharacterResponse)
async def create_tracked_character(
    book_id: str,
    character: CharacterCreate,
    db: Session = Depends(get_db),
):
    """Start tracking a character."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    new_char = TrackedCharacter(
        memory_id=memory.id,
        name=character.name,
        description=character.description,
        first_appearance_unit_id=character.first_appearance_unit_id,
    )
    db.add(new_char)
    db.commit()
    db.refresh(new_char)

    return new_char


# =============================================================================
# USER NOTES ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}/notes", response_model=list[UserNoteResponse])
async def get_user_notes(
    book_id: str,
    unit_id: Optional[str] = None,
    note_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get user notes for a book."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    query = db.query(UserNote).filter(UserNote.memory_id == memory.id)

    if unit_id:
        query = query.filter(UserNote.reading_unit_id == unit_id)

    if note_type:
        try:
            nt = NoteType(note_type)
            query = query.filter(UserNote.note_type == nt)
        except ValueError:
            pass

    notes = query.order_by(UserNote.created_at.desc()).limit(limit).all()

    return notes


@router.post("/books/{book_id}/notes", response_model=UserNoteResponse)
async def create_user_note(
    book_id: str,
    note: UserNoteCreate,
    db: Session = Depends(get_db),
):
    """Create a user note."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    try:
        note_type_enum = NoteType(note.note_type)
    except ValueError:
        note_type_enum = NoteType.NOTE

    new_note = UserNote(
        memory_id=memory.id,
        reading_unit_id=note.reading_unit_id,
        content=note.content,
        note_type=note_type_enum,
        char_start=note.char_start,
        char_end=note.char_end,
    )
    db.add(new_note)

    # Award XP for notes
    xp_awards = {
        NoteType.HIGHLIGHT: 2,
        NoteType.NOTE: 5,
        NoteType.QUESTION: 5,
        NoteType.INSIGHT: 10,
        NoteType.CONNECTION: 15,
    }
    memory.xp_earned = (memory.xp_earned or 0) + xp_awards.get(note_type_enum, 5)

    # Check for first insight achievement
    if note_type_enum == NoteType.INSIGHT:
        insights_count = db.query(UserNote).filter(
            UserNote.memory_id == memory.id,
            UserNote.note_type == NoteType.INSIGHT,
        ).count()

        if insights_count == 0:  # This is the first one
            achievements = list(memory.achievements_unlocked or [])
            if AchievementType.FIRST_INSIGHT.value not in achievements:
                achievements.append(AchievementType.FIRST_INSIGHT.value)
                memory.achievements_unlocked = achievements
                memory.xp_earned += 50  # Achievement bonus

    db.commit()
    db.refresh(new_note)

    return new_note


# =============================================================================
# CONNECTIONS ENDPOINTS
# =============================================================================

@router.post("/books/{book_id}/connections")
async def create_connection(
    book_id: str,
    connection: ConnectionCreate,
    db: Session = Depends(get_db),
):
    """Create a connection between two passages."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    new_conn = Connection(
        memory_id=memory.id,
        source_unit_id=connection.source_unit_id,
        source_char_start=connection.source_char_start,
        source_char_end=connection.source_char_end,
        source_description=connection.source_description,
        target_unit_id=connection.target_unit_id,
        target_char_start=connection.target_char_start,
        target_char_end=connection.target_char_end,
        target_description=connection.target_description,
        connection_type=connection.connection_type,
    )
    db.add(new_conn)

    # Award XP for connections
    memory.xp_earned = (memory.xp_earned or 0) + 20

    # Check for connection hunter achievement
    connections_count = db.query(Connection).filter(Connection.memory_id == memory.id).count()
    if connections_count >= 9:  # This will be #10
        achievements = list(memory.achievements_unlocked or [])
        if AchievementType.CONNECTION_HUNTER.value not in achievements:
            achievements.append(AchievementType.CONNECTION_HUNTER.value)
            memory.achievements_unlocked = achievements
            memory.xp_earned += 100

    db.commit()

    return {"status": "created", "id": new_conn.id}
