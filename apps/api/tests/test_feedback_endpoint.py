"""Integration tests for the message feedback PATCH endpoint."""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
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


@pytest.fixture
def fb_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def fb_db(fb_engine):
    Session = sessionmaker(bind=fb_engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def fb_client(fb_db):
    with patch("app.main.init_db"):
        from app.main import app
        from app.db import get_db
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            try:
                yield fb_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
        app.dependency_overrides.clear()
        limiter.enabled = True


@pytest.fixture
def session_with_message(fb_db):
    db = fb_db
    book = Book(
        id=str(uuid.uuid4()),
        title="Feedback Test Book",
        author="Author",
        filename="fb.pdf",
        file_type="pdf",
        file_size_bytes=1000,
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
        char_end=500,
    )
    db.add(section)
    db.flush()

    session = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="warmup",
        is_active=True,
    )
    db.add(session)
    db.flush()

    message = Message(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role=MessageRole.FACILITATOR,
        content="Let's discuss the opening scene.",
    )
    db.add(message)
    db.commit()

    return {"session": session, "message": message, "book": book}


class TestFeedbackEndpoint:
    """Test PATCH /v1/sessions/{session_id}/messages/{message_id}/feedback."""

    def test_set_feedback_up(self, fb_client, session_with_message):
        session = session_with_message["session"]
        message = session_with_message["message"]

        resp = fb_client.patch(
            f"/v1/sessions/{session.id}/messages/{message.id}/feedback",
            json={"feedback": "up"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback"] == "up"
        assert data["id"] == message.id

    def test_set_feedback_down(self, fb_client, session_with_message):
        session = session_with_message["session"]
        message = session_with_message["message"]

        resp = fb_client.patch(
            f"/v1/sessions/{session.id}/messages/{message.id}/feedback",
            json={"feedback": "down"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback"] == "down"

    def test_clear_feedback(self, fb_client, session_with_message):
        session = session_with_message["session"]
        message = session_with_message["message"]

        # Set it first
        fb_client.patch(
            f"/v1/sessions/{session.id}/messages/{message.id}/feedback",
            json={"feedback": "up"},
        )
        # Clear it
        resp = fb_client.patch(
            f"/v1/sessions/{session.id}/messages/{message.id}/feedback",
            json={"feedback": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback"] is None

    def test_feedback_invalid_value(self, fb_client, session_with_message):
        session = session_with_message["session"]
        message = session_with_message["message"]

        resp = fb_client.patch(
            f"/v1/sessions/{session.id}/messages/{message.id}/feedback",
            json={"feedback": "sideways"},
        )
        assert resp.status_code == 422

    def test_feedback_session_not_found(self, fb_client, session_with_message):
        message = session_with_message["message"]
        resp = fb_client.patch(
            f"/v1/sessions/nonexistent/messages/{message.id}/feedback",
            json={"feedback": "up"},
        )
        assert resp.status_code == 404

    def test_feedback_message_not_found(self, fb_client, session_with_message):
        session = session_with_message["session"]
        resp = fb_client.patch(
            f"/v1/sessions/{session.id}/messages/nonexistent/feedback",
            json={"feedback": "up"},
        )
        assert resp.status_code == 404

    def test_feedback_message_wrong_session(self, fb_client, session_with_message, fb_db):
        """Message exists but belongs to a different session."""
        db = fb_db
        message = session_with_message["message"]
        book = session_with_message["book"]

        # Create another session
        other_session = DiscussionSession(
            id=str(uuid.uuid4()),
            book_id=book.id,
            mode=DiscussionMode.GUIDED,
            section_ids=[],
            current_phase="warmup",
            is_active=True,
        )
        db.add(other_session)
        db.commit()

        resp = fb_client.patch(
            f"/v1/sessions/{other_session.id}/messages/{message.id}/feedback",
            json={"feedback": "up"},
        )
        assert resp.status_code == 404

    def test_feedback_appears_in_messages_list(self, fb_client, session_with_message):
        """Feedback should appear in the GET messages endpoint."""
        session = session_with_message["session"]
        message = session_with_message["message"]

        # Set feedback
        fb_client.patch(
            f"/v1/sessions/{session.id}/messages/{message.id}/feedback",
            json={"feedback": "down"},
        )

        # Check messages list
        resp = fb_client.get(f"/v1/sessions/{session.id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["feedback"] == "down"
