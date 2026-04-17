"""Integration tests for the session endpoints.

These tests exercise the router layer with a real in-memory SQLite database.
Only the LLM provider is mocked — everything else (DB, retrieval selector,
discussion engine) runs for real.
"""
import json
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.db.models import (
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
from app.providers.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Fixtures — thread-safe SQLite for TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def integration_engine():
    """Create a thread-safe SQLite engine for integration tests.

    TestClient runs the ASGI app in a separate thread, so we need
    check_same_thread=False and StaticPool to share one connection.
    """
    from sqlalchemy.pool import StaticPool

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def integration_db(integration_engine):
    """Create a session bound to the shared engine."""
    Session = sessionmaker(bind=integration_engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def book_with_chunks(integration_db):
    """Create a completed book with one section and chunks."""
    db = integration_db
    book = Book(
        id=str(uuid.uuid4()),
        title="Integration Test Book",
        author="Test Author",
        filename="test.pdf",
        file_type="pdf",
        file_size_bytes=5000,
        ingest_status=IngestStatus.COMPLETED,
    )
    db.add(book)
    db.flush()

    section = Section(
        id=str(uuid.uuid4()),
        book_id=book.id,
        title="Chapter 1",
        section_type="chapter",
        order_index=0,
        char_start=0,
        char_end=600,
        reading_time_min=5,
        token_estimate=150,
    )
    db.add(section)
    db.flush()

    chunk_texts = [
        (
            "The theory of relativity fundamentally changed our understanding "
            "of space and time. Einstein proposed that the laws of physics are "
            "the same for all non-accelerating observers."
        ),
        (
            "Quantum mechanics describes nature at the smallest scales of "
            "energy levels of atoms and subatomic particles. It introduces "
            "the concept of wave-particle duality."
        ),
        (
            "The standard model of particle physics is the theory describing "
            "three of the four known fundamental forces. It classifies all "
            "known elementary particles."
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
        db.add(chunk)
        chunks.append(chunk)

    db.commit()
    return {"book": book, "section": section, "chunks": chunks, "db": db}


@pytest.fixture
def active_session(book_with_chunks):
    """Create an active discussion session."""
    db = book_with_chunks["db"]
    book = book_with_chunks["book"]
    section = book_with_chunks["section"]

    session = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="warmup",
        is_active=True,
    )
    db.add(session)
    db.commit()
    return {**book_with_chunks, "session": session}


@pytest.fixture
def client(integration_db):
    """Create a test client with overridden DB dependency.

    Patches init_db to skip PostgreSQL-specific commands (CREATE EXTENSION)
    and disables the rate limiter to avoid Redis dependency.
    """
    with patch("app.main.init_db"):
        from app.main import app
        from app.db import get_db
        from app.rate_limit import limiter

        # Disable rate limiting for tests (avoids Redis connection)
        limiter.enabled = False

        def override_get_db():
            try:
                yield integration_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
        app.dependency_overrides.clear()
        limiter.enabled = True


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/start
# ---------------------------------------------------------------------------


class TestStartSession:
    """Test session creation endpoint."""

    def test_start_session_success(self, client, book_with_chunks):
        """Starting a session with a valid book returns session data."""
        book = book_with_chunks["book"]
        resp = client.post(
            "/v1/sessions/start",
            json={
                "book_id": book.id,
                "mode": "guided",
                "time_budget_min": 20,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["book_id"] == book.id
        assert data["mode"] == "guided"
        assert data["is_active"] is True
        assert data["current_phase"] == "warmup"
        assert "session_id" in data

    def test_start_session_book_not_found(self, client):
        """Starting a session with a non-existent book returns 404."""
        resp = client.post(
            "/v1/sessions/start",
            json={"book_id": "nonexistent-id", "mode": "guided"},
        )
        assert resp.status_code == 404

    def test_start_session_invalid_mode(self, client, book_with_chunks):
        """Starting a session with an invalid mode returns 400."""
        book = book_with_chunks["book"]
        resp = client.post(
            "/v1/sessions/start",
            json={"book_id": book.id, "mode": "invalid_mode"},
        )
        assert resp.status_code == 400

    def test_start_session_persists_preferences(self, client, book_with_chunks):
        """Session preference payload is stored and returned."""
        book = book_with_chunks["book"]
        resp = client.post(
            "/v1/sessions/start",
            json={
                "book_id": book.id,
                "mode": "conversation",
                "discussion_style": "fun",
                "reader_goal": "Talk like a real book club",
                "voice_profile": "Warm studio host",
                "experience_mode": "audio",
                "desire_lens": "trans_woman",
                "adult_intensity": "frank",
                "erotic_focus": "glamour",
                "vibes": ["fun", "nightly"],
                # Adult preferences require the 18+ gate.
                "adult_confirmed": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferences"]["discussion_style"] == "fun"
        assert data["preferences"]["experience_mode"] == "audio"
        assert data["preferences"]["desire_lens"] == "trans_woman"
        assert data["preferences"]["adult_intensity"] == "frank"
        assert data["preferences"]["erotic_focus"] == "glamour"
        assert data["adult_confirmed"] is True

    def test_start_session_rejects_adult_prefs_without_confirmation(
        self, client, book_with_chunks
    ):
        """Adult preferences without adult_confirmed=True must be rejected."""
        book = book_with_chunks["book"]
        resp = client.post(
            "/v1/sessions/start",
            json={
                "book_id": book.id,
                "mode": "conversation",
                "discussion_style": "sexy",
                "desire_lens": "woman",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests: GET /v1/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestGetSession:
    """Test session retrieval endpoint."""

    def test_get_session_success(self, client, active_session):
        """Getting an existing session returns its details."""
        session = active_session["session"]
        resp = client.get(f"/v1/sessions/{session.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session.id
        assert data["is_active"] is True

    def test_get_session_not_found(self, client):
        """Getting a non-existent session returns 404."""
        resp = client.get("/v1/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_patch_session_preferences(self, client, active_session):
        """Preference updates can be changed after session start.

        Adult preferences require the 18+ confirmation to be set either
        beforehand or as part of the PATCH itself.
        """
        session = active_session["session"]
        resp = client.patch(
            f"/v1/sessions/{session.id}/preferences",
            json={
                "experience_mode": "audio",
                "reader_goal": "Notice the craft",
                "desire_lens": "gay_man",
                "adult_intensity": "suggestive",
                "erotic_focus": "power",
                "adult_confirmed": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferences"]["experience_mode"] == "audio"
        assert data["preferences"]["reader_goal"] == "Notice the craft"
        assert data["preferences"]["desire_lens"] == "gay_man"
        assert data["preferences"]["adult_intensity"] == "suggestive"
        assert data["preferences"]["erotic_focus"] == "power"
        assert data["adult_confirmed"] is True

    def test_patch_session_rejects_adult_without_confirmation(
        self, client, active_session
    ):
        """A PATCH that enters after-dark territory without confirmation is rejected."""
        session = active_session["session"]
        resp = client.patch(
            f"/v1/sessions/{session.id}/preferences",
            json={"desire_lens": "woman"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests: GET /v1/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    """Test message retrieval endpoint."""

    def test_get_messages_empty(self, client, active_session):
        """A new session has no messages."""
        session = active_session["session"]
        resp = client.get(f"/v1/sessions/{session.id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session.id
        assert data["messages"] == []

    def test_get_messages_with_content(self, client, active_session):
        """Messages are returned in chronological order."""
        session = active_session["session"]
        db = active_session["db"]

        msg1 = Message(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=MessageRole.USER,
            content="What is relativity?",
        )
        msg2 = Message(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=MessageRole.FACILITATOR,
            content="Relativity is a theory by Einstein.",
        )
        db.add(msg1)
        db.add(msg2)
        db.commit()

        resp = client.get(f"/v1/sessions/{session.id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "facilitator"

    def test_get_messages_session_not_found(self, client):
        """Getting messages for a non-existent session returns 404."""
        resp = client.get("/v1/sessions/nonexistent-id/messages")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/advance-phase
# ---------------------------------------------------------------------------


class TestAdvancePhase:
    """Test phase advancement endpoint."""

    def test_advance_phase_success(self, client, active_session):
        """Advancing phase returns the new phase."""
        session = active_session["session"]
        with patch("app.routers.sessions.DiscussionEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.advance_phase.return_value = "deep_dive"

            resp = client.post(f"/v1/sessions/{session.id}/advance-phase")
            assert resp.status_code == 200
            data = resp.json()
            assert data["session_id"] == session.id
            assert data["new_phase"] == "deep_dive"

    def test_advance_phase_not_found(self, client):
        """Advancing phase on a non-existent session returns 404."""
        resp = client.post("/v1/sessions/nonexistent-id/advance-phase")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/end
# ---------------------------------------------------------------------------


class TestEndSession:
    """Test session ending endpoint."""

    def test_end_session_success(self, client, active_session):
        """Ending a session marks it as inactive."""
        session = active_session["session"]
        resp = client.post(f"/v1/sessions/{session.id}/end")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ended"

    def test_end_session_not_found(self, client):
        """Ending a non-existent session returns 404."""
        resp = client.post("/v1/sessions/nonexistent-id/end")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/message
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Test the synchronous message endpoint."""

    def test_send_message_session_not_found(self, client):
        """Sending a message to a non-existent session returns 404."""
        resp = client.post(
            "/v1/sessions/nonexistent-id/message",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    def test_send_message_inactive_session(self, client, active_session):
        """Sending a message to an ended session returns 400."""
        session = active_session["session"]
        db = active_session["db"]
        session.is_active = False
        db.commit()

        resp = client.post(
            f"/v1/sessions/{session.id}/message",
            json={"content": "Hello"},
        )
        assert resp.status_code == 400

    def test_send_message_empty_content(self, client, active_session):
        """Sending an empty message fails validation."""
        session = active_session["session"]
        resp = client.post(
            f"/v1/sessions/{session.id}/message",
            json={"content": ""},
        )
        assert resp.status_code == 422  # Pydantic validation error

    def test_send_message_success(self, client, active_session):
        """Sending a valid message returns agent responses."""
        session = active_session["session"]

        with patch("app.routers.sessions.DiscussionEngine") as MockEngine:
            from app.discussion.agents import AgentResponse

            mock_engine = MockEngine.return_value
            mock_engine.process_user_message = AsyncMock(
                return_value=[
                    AgentResponse(
                        agent_type="facilitator",
                        content="Great question about relativity!",
                        citations=[],
                    ),
                ]
            )

            resp = client.post(
                f"/v1/sessions/{session.id}/message",
                json={"content": "Tell me about relativity"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["messages"]) == 1
            assert data["messages"][0]["role"] == "facilitator"
            assert "relativity" in data["messages"][0]["content"]


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/message/stream
# ---------------------------------------------------------------------------


class TestStreamMessage:
    """Test the SSE streaming endpoint."""

    def test_stream_session_not_found(self, client):
        """Streaming from a non-existent session returns 404."""
        resp = client.post(
            "/v1/sessions/nonexistent-id/message/stream",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    def test_stream_inactive_session(self, client, active_session):
        """Streaming from an ended session returns 400."""
        session = active_session["session"]
        db = active_session["db"]
        session.is_active = False
        db.commit()

        resp = client.post(
            f"/v1/sessions/{session.id}/message/stream",
            json={"content": "Hello"},
        )
        assert resp.status_code == 400

    def test_stream_message_success(self, client, active_session):
        """Streaming returns SSE events with proper structure."""
        session = active_session["session"]

        async def mock_stream_user_message(*args, **kwargs):
            yield {
                "type": "message_start",
                "event_id": "evt_1",
                "turn_id": "test-turn",
                "agent_id": "facilitator",
                "sequence": 1,
                "role": "facilitator",
                "session_id": session.id,
            }
            yield {
                "type": "message_delta",
                "event_id": "evt_2",
                "turn_id": "test-turn",
                "agent_id": "facilitator",
                "sequence": 2,
                "role": "facilitator",
                "session_id": session.id,
                "delta": "Hello there!",
            }
            yield {
                "type": "message_end",
                "event_id": "evt_3",
                "turn_id": "test-turn",
                "agent_id": "facilitator",
                "sequence": 3,
                "role": "facilitator",
                "session_id": session.id,
                "message_id": "message-123",
                "content": "Hello there!",
                "citations": [],
                "citation_quality": None,
                "token_usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            }
            yield {
                "type": "done",
                "event_id": "evt_4",
                "turn_id": "test-turn",
                "sequence": 4,
                "turn_metrics": {
                    "turn_id": "test-turn",
                    "total_ms": 100.0,
                    "ttft_ms": 50.0,
                    "stages": [],
                },
            }

        with patch("app.routers.sessions.DiscussionEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.stream_user_message = mock_stream_user_message

            resp = client.post(
                f"/v1/sessions/{session.id}/message/stream",
                json={"content": "Tell me about physics"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            # Parse SSE events from the response
            events = []
            for line in resp.text.strip().split("\n"):
                if line.startswith("data: "):
                    event_data = json.loads(line[6:])
                    events.append(event_data)

            # Verify event sequence
            assert len(events) >= 3
            event_types = [e["type"] for e in events]
            assert "message_start" in event_types
            assert "message_end" in event_types
            assert "done" in event_types

            # Verify done event includes turn_metrics
            done_event = next(e for e in events if e["type"] == "done")
            assert "turn_metrics" in done_event

            # Verify message_end has expected fields
            end_event = next(e for e in events if e["type"] == "message_end")
            assert "content" in end_event
            assert "citations" in end_event
            assert "token_usage" in end_event
            assert end_event["session_id"] == session.id
            assert end_event["message_id"] == "message-123"


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Test the summary generation endpoint."""

    def test_summary_success(self, client, active_session):
        """Generating a summary returns text."""
        session = active_session["session"]

        with patch("app.routers.sessions.DiscussionEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.generate_summary = AsyncMock(
                return_value="This discussion covered key physics concepts."
            )

            resp = client.post(f"/v1/sessions/{session.id}/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert "summary" in data
            assert data["session_id"] == session.id

    def test_summary_not_found(self, client):
        """Summary for non-existent session returns 404."""
        resp = client.post("/v1/sessions/nonexistent-id/summary")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/challenge
# ---------------------------------------------------------------------------


class TestChallenge:
    """Test the skeptic challenge endpoint."""

    def test_challenge_success(self, client, active_session):
        """Challenging a claim returns a skeptic response."""
        session = active_session["session"]

        with patch("app.routers.sessions.DiscussionEngine") as MockEngine:
            from app.discussion.agents import AgentResponse

            mock_engine = MockEngine.return_value
            mock_engine.get_skeptic_response = AsyncMock(
                return_value=AgentResponse(
                    agent_type="skeptic",
                    content="That claim lacks evidence.",
                    citations=[],
                )
            )

            resp = client.post(
                f"/v1/sessions/{session.id}/challenge",
                params={"claim": "Relativity is simple"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "skeptic"

    def test_challenge_not_found(self, client):
        """Challenge on a non-existent session returns 404."""
        resp = client.post(
            "/v1/sessions/nonexistent-id/challenge",
            params={"claim": "test"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /v1/sessions/{session_id}/end (idempotency)
# ---------------------------------------------------------------------------


class TestEndSessionIdempotency:
    """Test that ending a session is idempotent."""

    def test_end_already_ended(self, client, active_session):
        """Ending an already-ended session still succeeds."""
        session = active_session["session"]
        # End once
        resp1 = client.post(f"/v1/sessions/{session.id}/end")
        assert resp1.status_code == 200
        # End again
        resp2 = client.post(f"/v1/sessions/{session.id}/end")
        assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# Tests: Session message limit guard
# ---------------------------------------------------------------------------


class TestMessageLimit:
    """Test that the session message limit is enforced."""

    def test_message_limit_enforced(self, client, active_session):
        """When message limit is reached, further messages are rejected."""
        session = active_session["session"]
        db = active_session["db"]

        with patch("app.routers.sessions.settings") as mock_settings:
            mock_settings.max_session_messages = 2

            # Add messages up to the limit
            for i in range(2):
                msg = Message(
                    id=str(uuid.uuid4()),
                    session_id=session.id,
                    role=MessageRole.USER,
                    content=f"Message {i}",
                )
                db.add(msg)
            db.commit()

            resp = client.post(
                f"/v1/sessions/{session.id}/message",
                json={"content": "One more message"},
            )
            assert resp.status_code == 400
            assert "limit" in resp.json()["detail"].lower()
