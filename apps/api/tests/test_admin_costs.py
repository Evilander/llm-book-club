"""Tests for the admin cost tracking endpoint."""
import uuid
from datetime import datetime, timedelta
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def admin_db(admin_engine):
    Session = sessionmaker(bind=admin_engine)
    db = Session()
    yield db
    db.close()


@pytest.fixture
def admin_client(admin_db):
    with patch("app.main.init_db"):
        from app.main import app
        from app.db import get_db
        from app.rate_limit import limiter

        limiter.enabled = False

        def override_get_db():
            try:
                yield admin_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
        app.dependency_overrides.clear()
        limiter.enabled = True


@pytest.fixture
def book_with_sessions(admin_db):
    """Create a book with two sessions and messages with token usage metadata."""
    db = admin_db
    book = Book(
        id=str(uuid.uuid4()),
        title="Cost Test Book",
        author="Test Author",
        filename="cost.pdf",
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
        char_end=500,
        reading_time_min=5,
        token_estimate=100,
    )
    db.add(section)
    db.flush()

    # Session 1 with messages that have token usage
    session1 = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="warmup",
        is_active=True,
    )
    db.add(session1)
    db.flush()

    msg1 = Message(
        id=str(uuid.uuid4()),
        session_id=session1.id,
        role=MessageRole.FACILITATOR,
        content="Welcome to the discussion.",
        metadata_json={
            "token_usage": {
                "input_tokens": 1000,
                "output_tokens": 200,
                "total_tokens": 1200,
            }
        },
    )
    msg2 = Message(
        id=str(uuid.uuid4()),
        session_id=session1.id,
        role=MessageRole.CLOSE_READER,
        content="Let me look more closely.",
        metadata_json={
            "token_usage": {
                "input_tokens": 1500,
                "output_tokens": 300,
                "total_tokens": 1800,
            }
        },
    )
    # A user message with no token usage
    msg3 = Message(
        id=str(uuid.uuid4()),
        session_id=session1.id,
        role=MessageRole.USER,
        content="Tell me more.",
    )
    db.add_all([msg1, msg2, msg3])

    # Session 2 with one message
    session2 = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=book.id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="warmup",
        is_active=True,
    )
    db.add(session2)
    db.flush()

    msg4 = Message(
        id=str(uuid.uuid4()),
        session_id=session2.id,
        role=MessageRole.SKEPTIC,
        content="I disagree.",
        metadata_json={
            "token_usage": {
                "input_tokens": 800,
                "output_tokens": 150,
                "total_tokens": 950,
            }
        },
    )
    db.add(msg4)
    db.commit()

    return {
        "book": book,
        "section": section,
        "session1": session1,
        "session2": session2,
        "messages": [msg1, msg2, msg3, msg4],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCostEndpoint:
    """Test GET /v1/admin/costs."""

    def test_costs_basic(self, admin_client, book_with_sessions):
        resp = admin_client.get("/v1/admin/costs")
        assert resp.status_code == 200
        data = resp.json()

        # Total tokens: 1000+200 + 1500+300 + 800+150 = 3950
        assert data["total_input_tokens"] == 3300  # 1000+1500+800
        assert data["total_output_tokens"] == 650  # 200+300+150
        assert data["total_tokens"] == 3950
        assert data["total_cost_estimate"] > 0
        assert data["days"] == 30
        assert data["book_id"] is None

    def test_costs_per_session_breakdown(self, admin_client, book_with_sessions):
        resp = admin_client.get("/v1/admin/costs")
        data = resp.json()

        session1_id = book_with_sessions["session1"].id
        session2_id = book_with_sessions["session2"].id

        assert session1_id in data["per_session"]
        assert session2_id in data["per_session"]

        s1 = data["per_session"][session1_id]
        assert s1["input_tokens"] == 2500  # 1000+1500
        assert s1["output_tokens"] == 500  # 200+300
        assert s1["message_count"] == 2  # user message has no usage -> skipped

        s2 = data["per_session"][session2_id]
        assert s2["input_tokens"] == 800
        assert s2["output_tokens"] == 150
        assert s2["message_count"] == 1

    def test_costs_per_agent_breakdown(self, admin_client, book_with_sessions):
        resp = admin_client.get("/v1/admin/costs")
        data = resp.json()

        assert "facilitator" in data["per_agent"]
        assert "close_reader" in data["per_agent"]
        assert "skeptic" in data["per_agent"]
        # user has no token usage, so should not appear
        assert "user" not in data["per_agent"]

        assert data["per_agent"]["facilitator"]["input_tokens"] == 1000
        assert data["per_agent"]["close_reader"]["input_tokens"] == 1500
        assert data["per_agent"]["skeptic"]["input_tokens"] == 800

    def test_costs_filter_by_book(self, admin_client, book_with_sessions):
        book_id = book_with_sessions["book"].id
        resp = admin_client.get(f"/v1/admin/costs?book_id={book_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["book_id"] == book_id
        assert data["total_tokens"] == 3950

    def test_costs_filter_by_nonexistent_book(self, admin_client, book_with_sessions):
        resp = admin_client.get("/v1/admin/costs?book_id=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == 0

    def test_costs_days_param(self, admin_client, book_with_sessions):
        resp = admin_client.get("/v1/admin/costs?days=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["days"] == 1
        # Messages were just created, so they should be within 1 day
        assert data["total_tokens"] == 3950

    def test_costs_empty_database(self, admin_client):
        resp = admin_client.get("/v1/admin/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == 0
        assert data["total_cost_estimate"] == 0
        assert data["per_session"] == {}
        assert data["per_agent"] == {}

    def test_costs_cost_calculation(self, admin_client, book_with_sessions):
        """Verify the cost estimate uses the documented pricing."""
        resp = admin_client.get("/v1/admin/costs")
        data = resp.json()

        # Expected: 3300 * $3/M + 650 * $15/M
        expected_cost = 3300 * 3.0 / 1_000_000 + 650 * 15.0 / 1_000_000
        assert abs(data["total_cost_estimate"] - round(expected_cost, 6)) < 1e-9
