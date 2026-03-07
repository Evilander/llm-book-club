"""
Memory and Progress API Endpoints

Endpoints for:
- Book memory (key moments, themes, characters, notes)
- Reading progress and units
- Quizzes and comprehension checks
- Gamification (XP, achievements, streaks)
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
    NoteType, Connection, QuizResult as QuizResultModel,
    UserProgress, DailyActivity, AchievementType,
)
from ..providers.llm.factory import get_llm_client
from ..discussion.quiz_system import (
    QuizGenerator, AdaptiveQuizGenerator, QuizContext,
    Quiz, QuizResult, ComprehensionChecker,
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


class QuizSubmission(BaseModel):
    answers: list[int]  # Answer indices for each question


class GamificationStats(BaseModel):
    xp_earned: int
    current_level: int
    xp_to_next_level: int
    achievements: list[str]
    current_streak: int
    longest_streak: int


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


# =============================================================================
# QUIZ ENDPOINTS
# =============================================================================

@router.post("/books/{book_id}/units/{unit_id}/quiz")
async def generate_quiz(
    book_id: str,
    unit_id: str,
    num_questions: int = Query(5, ge=3, le=7),
    db: Session = Depends(get_db),
):
    """Generate a quiz for a reading unit."""
    unit = db.query(ReadingUnit).filter(
        ReadingUnit.id == unit_id,
        ReadingUnit.book_id == book_id,
    ).first()

    if not unit:
        raise HTTPException(status_code=404, detail="Reading unit not found")

    # Get unit text from chunks
    from ..db.models import Chunk
    chunks = db.query(Chunk).filter(Chunk.reading_unit_id == unit_id).order_by(Chunk.order_index).all()
    unit_text = "\n\n".join(c.text for c in chunks)

    if not unit_text:
        raise HTTPException(status_code=400, detail="No text found for this unit")

    # Get memory context
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()

    context = QuizContext(
        unit_text=unit_text,
        unit_title=unit.title,
        unit_id=unit_id,
    )

    if memory:
        # Add memory context
        context.previous_units = memory.units_completed
        context.key_moments = [
            {"text": m.quote_text, "significance": m.significance}
            for m in (memory.key_moments or [])[:5]
        ]
        context.tracked_themes = [
            {"name": t.name, "description": t.description}
            for t in (memory.themes or [])[:5]
        ]

    # Generate quiz
    llm = get_llm_client()
    generator = AdaptiveQuizGenerator(llm)

    quiz = await generator.generate_adaptive_quiz(context)

    return {
        "unit_id": unit_id,
        "unit_title": unit.title,
        "questions": [q.model_dump() for q in quiz.questions],
        "total_xp": quiz.total_xp,
    }


@router.post("/books/{book_id}/units/{unit_id}/quiz/submit")
async def submit_quiz(
    book_id: str,
    unit_id: str,
    submission: QuizSubmission,
    db: Session = Depends(get_db),
):
    """Submit quiz answers and get results."""
    # In a real implementation, we'd store the quiz and validate against it
    # For now, we'll generate a new quiz and grade against that

    unit = db.query(ReadingUnit).filter(
        ReadingUnit.id == unit_id,
        ReadingUnit.book_id == book_id,
    ).first()

    if not unit:
        raise HTTPException(status_code=404, detail="Reading unit not found")

    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    # Store quiz result
    correct_count = len([a for a in submission.answers if a >= 0])  # Simplified
    total = len(submission.answers)
    score_pct = (correct_count / total * 100) if total > 0 else 0

    # Calculate XP
    xp_earned = int(score_pct / 10) * 10  # Rough calculation

    quiz_result = QuizResultModel(
        memory_id=memory.id,
        reading_unit_id=unit_id,
        score_pct=score_pct,
        xp_earned=xp_earned,
        questions_data={"answers": submission.answers},
    )
    db.add(quiz_result)

    # Update memory XP
    memory.xp_earned = (memory.xp_earned or 0) + xp_earned

    # Update avg quiz score
    all_results = db.query(QuizResultModel).filter(QuizResultModel.memory_id == memory.id).all()
    if all_results:
        memory.avg_quiz_score = sum(r.score_pct for r in all_results) / len(all_results)

    db.commit()

    return {
        "score_pct": score_pct,
        "correct_count": correct_count,
        "total_count": total,
        "xp_earned": xp_earned,
    }


# =============================================================================
# GAMIFICATION ENDPOINTS
# =============================================================================

@router.get("/books/{book_id}/stats", response_model=GamificationStats)
async def get_gamification_stats(
    book_id: str,
    db: Session = Depends(get_db),
):
    """Get gamification stats for a book."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    xp = memory.xp_earned or 0
    level = 1 + (xp // 500)
    xp_in_level = xp % 500
    xp_to_next = 500 - xp_in_level

    # Calculate streak
    today = date.today()
    activities = db.query(DailyActivity).filter(
        DailyActivity.memory_id == memory.id
    ).order_by(DailyActivity.date.desc()).limit(30).all()

    current_streak = 0
    for i, activity in enumerate(activities):
        expected_date = today - timedelta(days=i)
        if activity.date == expected_date:
            current_streak += 1
        else:
            break

    # Get longest streak from progress if tracked
    longest_streak = current_streak

    return GamificationStats(
        xp_earned=xp,
        current_level=level,
        xp_to_next_level=xp_to_next,
        achievements=memory.achievements_unlocked or [],
        current_streak=current_streak,
        longest_streak=longest_streak,
    )


from datetime import timedelta


@router.get("/books/{book_id}/achievements")
async def get_available_achievements(book_id: str, db: Session = Depends(get_db)):
    """Get all achievements and their unlock status."""
    memory = db.query(BookMemory).filter(BookMemory.book_id == book_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Book memory not found")

    unlocked = set(memory.achievements_unlocked or [])

    all_achievements = [
        {
            "id": AchievementType.FIRST_INSIGHT.value,
            "name": "First Insight",
            "description": "Record your first insight",
            "xp_reward": 50,
            "unlocked": AchievementType.FIRST_INSIGHT.value in unlocked,
        },
        {
            "id": AchievementType.BOOKWORM_7.value,
            "name": "Bookworm",
            "description": "Read for 7 days in a row",
            "xp_reward": 100,
            "unlocked": AchievementType.BOOKWORM_7.value in unlocked,
        },
        {
            "id": AchievementType.COMPLETIONIST.value,
            "name": "Completionist",
            "description": "Finish an entire book",
            "xp_reward": 500,
            "unlocked": AchievementType.COMPLETIONIST.value in unlocked,
        },
        {
            "id": AchievementType.CONNECTION_HUNTER.value,
            "name": "Connection Hunter",
            "description": "Find 10 cross-chapter connections",
            "xp_reward": 100,
            "unlocked": AchievementType.CONNECTION_HUNTER.value in unlocked,
        },
        {
            "id": AchievementType.QUIZ_MASTER.value,
            "name": "Quiz Master",
            "description": "Score 100% on 5 quizzes",
            "xp_reward": 150,
            "unlocked": AchievementType.QUIZ_MASTER.value in unlocked,
        },
        {
            "id": AchievementType.DEEP_READER.value,
            "name": "Deep Reader",
            "description": "Mark 20 key moments",
            "xp_reward": 75,
            "unlocked": AchievementType.DEEP_READER.value in unlocked,
        },
        {
            "id": AchievementType.THEME_TRACKER.value,
            "name": "Theme Tracker",
            "description": "Track 5 themes",
            "xp_reward": 50,
            "unlocked": AchievementType.THEME_TRACKER.value in unlocked,
        },
    ]

    return all_achievements
