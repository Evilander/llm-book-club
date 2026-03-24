"""Discussion session endpoints."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db, Book, DiscussionSession, Message, DiscussionMode, MessageRole
from ..retrieval.selector import select_session_slice
from ..discussion.engine import DiscussionEngine
from ..rate_limit import limiter
from ..settings import settings

router = APIRouter(tags=["sessions"])


class StartSessionRequest(BaseModel):
    book_id: str
    mode: str = "guided"  # guided|socratic|poetry|nonfiction
    time_budget_min: int = 20
    section_ids: list[str] | None = None  # if None: auto-select
    start_section_id: str | None = None  # start from this section
    discussion_style: str | None = None
    vibes: list[str] | None = None
    voice_profile: str | None = None
    reader_goal: str | None = None
    experience_mode: str | None = None
    desire_lens: str | None = None
    adult_intensity: str | None = None
    erotic_focus: str | None = None


class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    include_close_reader: bool = True
    adaptive: bool = True  # Use MARS-style adaptive agent selection


class SessionPreferencesUpdateRequest(BaseModel):
    discussion_style: str | None = None
    vibes: list[str] | None = None
    voice_profile: str | None = None
    reader_goal: str | None = None
    experience_mode: str | None = None
    desire_lens: str | None = None
    adult_intensity: str | None = None
    erotic_focus: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    book_id: str
    mode: str
    time_budget_min: int
    current_phase: str
    sections: list[dict]
    is_active: bool
    preferences: dict | None = None


class MessageResponse(BaseModel):
    role: str
    content: str
    citations: list[dict] | None


class DiscussionResponse(BaseModel):
    messages: list[MessageResponse]


@router.post("/sessions/start", response_model=SessionResponse)
@limiter.limit("5/minute")
def start_session(request: Request, req: StartSessionRequest, db: Session = Depends(get_db)):
    """
    Start a new discussion session for a book.

    Selects a reading slice based on time budget and creates the session.
    """
    # Verify book exists and is processed
    book = db.query(Book).filter(Book.id == req.book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")
    if book.ingest_status.value != "completed":
        raise HTTPException(400, f"Book not ready. Status: {book.ingest_status.value}")

    # Validate mode
    try:
        mode = DiscussionMode(req.mode)
    except ValueError:
        raise HTTPException(400, f"Invalid mode: {req.mode}")

    # Select reading slice
    try:
        slice_data = select_session_slice(
            db=db,
            book_id=req.book_id,
            time_budget_min=req.time_budget_min,
            start_section_id=req.start_section_id,
            section_ids=req.section_ids,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Create session
    session = DiscussionSession(
        book_id=req.book_id,
        mode=mode,
        time_budget_min=req.time_budget_min,
        section_ids=slice_data.section_ids,
        current_phase="warmup",
        is_active=True,
        preferences_json={
            "discussion_style": req.discussion_style,
            "vibes": req.vibes or [],
            "voice_profile": req.voice_profile,
            "reader_goal": req.reader_goal,
            "experience_mode": req.experience_mode or "text",
            "desire_lens": req.desire_lens,
            "adult_intensity": req.adult_intensity,
            "erotic_focus": req.erotic_focus,
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionResponse(
        session_id=session.id,
        book_id=session.book_id,
        mode=session.mode.value,
        time_budget_min=session.time_budget_min,
        current_phase=session.current_phase,
        sections=slice_data.sections,
        is_active=session.is_active,
        preferences=session.preferences_json,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    """Get session details."""
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # Get sections
    from ..db import Section
    sections = (
        db.query(Section)
        .filter(Section.id.in_(session.section_ids))
        .order_by(Section.order_index)
        .all()
    )

    return SessionResponse(
        session_id=session.id,
        book_id=session.book_id,
        mode=session.mode.value,
        time_budget_min=session.time_budget_min,
        current_phase=session.current_phase,
        sections=[
            {
                "id": s.id,
                "title": s.title,
                "section_type": s.section_type,
                "order_index": s.order_index,
                "reading_time_min": s.reading_time_min,
            }
            for s in sections
        ],
        is_active=session.is_active,
        preferences=session.preferences_json,
    )


@router.patch("/sessions/{session_id}/preferences")
def update_session_preferences(
    session_id: str,
    req: SessionPreferencesUpdateRequest,
    db: Session = Depends(get_db),
):
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    existing = dict(session.preferences_json or {})
    updates = req.model_dump(exclude_none=True)
    existing.update(updates)
    session.preferences_json = existing
    db.commit()
    db.refresh(session)

    return {"session_id": session.id, "preferences": session.preferences_json}


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    """Get all messages in a session."""
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at)
        .all()
    )

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role.value,
                "content": m.content,
                "citations": m.citations,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.post("/sessions/{session_id}/start-discussion", response_model=DiscussionResponse)
async def start_discussion(session_id: str, db: Session = Depends(get_db)):
    """
    Start the discussion with opening questions from the facilitator.
    """
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # Idempotent: if messages already exist, return them instead of creating duplicates
    existing = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at)
        .all()
    )
    if existing:
        return DiscussionResponse(
            messages=[
                MessageResponse(
                    role=m.role.value,
                    content=m.content,
                    citations=m.citations,
                )
                for m in existing
            ]
        )

    # Get slice data
    slice_data = select_session_slice(
        db=db,
        book_id=session.book_id,
        section_ids=session.section_ids,
    )

    # Create discussion engine
    engine = DiscussionEngine(db, session, slice_data)

    # Generate opening
    response = await engine.start_discussion()

    return DiscussionResponse(
        messages=[
            MessageResponse(
                role="facilitator",
                content=response.content,
                citations=DiscussionEngine._serialize_citations(response.citations),
            )
        ]
    )


@router.post("/sessions/{session_id}/message", response_model=DiscussionResponse)
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    session_id: str,
    req: MessageRequest,
    db: Session = Depends(get_db),
):
    """
    Send a message and get agent responses.
    """
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.is_active:
        raise HTTPException(400, "Session is no longer active")

    # Guard: enforce max messages per session
    msg_count = db.query(Message).filter(Message.session_id == session_id).count()
    if settings.max_session_messages > 0 and msg_count >= settings.max_session_messages:
        raise HTTPException(
            400,
            f"Session message limit reached ({settings.max_session_messages}). "
            "Please start a new session.",
        )

    # Get slice data
    slice_data = select_session_slice(
        db=db,
        book_id=session.book_id,
        section_ids=session.section_ids,
    )

    # Create discussion engine
    engine = DiscussionEngine(db, session, slice_data)

    # Process message
    responses = await engine.process_user_message(
        req.content,
        include_close_reader=req.include_close_reader,
        adaptive=req.adaptive,
    )

    return DiscussionResponse(
        messages=[
            MessageResponse(
                role=r.agent_type,
                content=r.content,
                citations=DiscussionEngine._serialize_citations(r.citations),
            )
            for r in responses
        ]
    )


@router.post("/sessions/{session_id}/message/stream")
@limiter.limit("20/minute")
async def stream_message(
    request: Request,
    session_id: str,
    req: MessageRequest,
    db: Session = Depends(get_db),
):
    """Send a message and stream agent responses as server-sent events."""
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.is_active:
        raise HTTPException(400, "Session is no longer active")

    # Guard: enforce max messages per session
    msg_count = db.query(Message).filter(Message.session_id == session_id).count()
    if settings.max_session_messages > 0 and msg_count >= settings.max_session_messages:
        raise HTTPException(
            400,
            f"Session message limit reached ({settings.max_session_messages}). "
            "Please start a new session.",
        )

    slice_data = select_session_slice(
        db=db,
        book_id=session.book_id,
        section_ids=session.section_ids,
    )

    engine = DiscussionEngine(db, session, slice_data)

    async def generate():
        try:
            async for event in engine.stream_user_message(
                req.content,
                include_close_reader=req.include_close_reader,
                adaptive=req.adaptive,
            ):
                event_id = event.get("event_id", "")
                payload = json.dumps(event, ensure_ascii=False)
                yield f"id: {event_id}\ndata: {payload}\n\n"
        except Exception as e:
            payload = json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/challenge")
async def challenge_claim(
    session_id: str,
    claim: str,
    db: Session = Depends(get_db),
):
    """
    Get a skeptic's challenge to a claim.
    """
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # Get slice data
    slice_data = select_session_slice(
        db=db,
        book_id=session.book_id,
        section_ids=session.section_ids,
    )

    engine = DiscussionEngine(db, session, slice_data)
    response = await engine.get_skeptic_response(claim)

    return MessageResponse(
        role="skeptic",
        content=response.content,
        citations=DiscussionEngine._serialize_citations(response.citations),
    )


@router.post("/sessions/{session_id}/advance-phase")
def advance_phase(session_id: str, db: Session = Depends(get_db)):
    """Advance to the next discussion phase."""
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # Get slice data
    slice_data = select_session_slice(
        db=db,
        book_id=session.book_id,
        section_ids=session.section_ids,
    )

    engine = DiscussionEngine(db, session, slice_data)
    new_phase = engine.advance_phase()

    return {"session_id": session_id, "new_phase": new_phase}


@router.post("/sessions/{session_id}/summary")
async def generate_summary(session_id: str, db: Session = Depends(get_db)):
    """Generate a summary of the discussion."""
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    # Get slice data
    slice_data = select_session_slice(
        db=db,
        book_id=session.book_id,
        section_ids=session.section_ids,
    )

    engine = DiscussionEngine(db, session, slice_data)
    summary = await engine.generate_summary()

    return {"session_id": session_id, "summary": summary}


@router.post("/sessions/{session_id}/end")
def end_session(session_id: str, db: Session = Depends(get_db)):
    """End a discussion session."""
    session = db.query(DiscussionSession).filter(DiscussionSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    session.is_active = False
    db.commit()

    return {"session_id": session_id, "status": "ended"}
