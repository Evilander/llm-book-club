"""Tests for the message feedback feature (thumbs up/down)."""
import uuid

import pytest

from app.db.models import (
    Message,
    MessageRole,
)


class TestMessageFeedbackModel:
    """Test the feedback column on Message model."""

    def test_message_default_feedback_is_none(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.FACILITATOR,
            content="Some response.",
        )
        mock_db.add(msg)
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.feedback is None

    def test_message_feedback_up(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.FACILITATOR,
            content="Good response.",
            feedback="up",
        )
        mock_db.add(msg)
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.feedback == "up"

    def test_message_feedback_down(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.FACILITATOR,
            content="Bad response.",
            feedback="down",
        )
        mock_db.add(msg)
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.feedback == "down"

    def test_message_feedback_can_be_updated(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.FACILITATOR,
            content="Changeable response.",
            feedback="up",
        )
        mock_db.add(msg)
        mock_db.commit()

        msg.feedback = "down"
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.feedback == "down"

    def test_message_feedback_can_be_cleared(self, mock_db, sample_session):
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=sample_session.id,
            role=MessageRole.FACILITATOR,
            content="Clearable response.",
            feedback="up",
        )
        mock_db.add(msg)
        mock_db.commit()

        msg.feedback = None
        mock_db.commit()
        mock_db.refresh(msg)
        assert msg.feedback is None
