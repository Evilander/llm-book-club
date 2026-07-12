"""Direct DiscussionEngine tests for the validated-first grounded streaming branch.

These prove the engine-level contract the route tests cannot (they mock the
engine): raw provider JSON and rejected claims never reach message_delta or
sentence_ready, message_end matches the persisted row, and the streaming and
non-streaming paths produce identical grounded output.
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

from app.db.models import DiscussionMode, DiscussionSession, Message, MessageRole
from app.discussion.engine import DiscussionEngine
from app.providers.llm.base import StructuredLLMResponse
from app.retrieval.search import SearchResult
from app.retrieval.selector import SessionSlice

VALID_QUOTE = "The morning sun cast long shadows"
REJECTED_MARKER = "REJECTED-CLAIM"


class StructuredStub:
    def __init__(self, *payloads: dict):
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    async def complete_structured(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        payload = self.payloads.pop(0)
        return StructuredLLMResponse(
            content=json.dumps(payload),
            parsed=payload,
            input_tokens=10,
            output_tokens=5,
        )


def grounded_payload(chunk_id: str, *, include_unsupported: bool = False) -> dict:
    segments = [
        {
            "id": "claim",
            "kind": "interpretation",
            "text": "The long shadows hold the scene in suspension.",
            "citation_ids": ["evidence"],
        },
        {
            "id": "question",
            "kind": "question",
            "text": "Does the stillness read as peace or dread to you?",
            "citation_ids": [],
        },
    ]
    citations = [{"id": "evidence", "chunk_id": chunk_id, "quote": VALID_QUOTE}]
    if include_unsupported:
        segments.insert(
            1,
            {
                "id": "shaky",
                "kind": "grounded_claim",
                "text": f"{REJECTED_MARKER} the oak tree secretly symbolizes empire.",
                "citation_ids": ["fake"],
            },
        )
        citations.append(
            {"id": "fake", "chunk_id": chunk_id, "quote": "totally fabricated quote"}
        )
    return {"segments": segments, "citations": citations}


def build_engine(mock_db, sample_book, llm) -> tuple[DiscussionEngine, DiscussionSession]:
    section = sample_book["section"]
    chunks = sample_book["chunks"]
    session = DiscussionSession(
        id=str(uuid.uuid4()),
        book_id=sample_book["book"].id,
        mode=DiscussionMode.GUIDED,
        section_ids=[section.id],
        current_phase="warmup",
        is_active=True,
    )
    mock_db.add(session)
    mock_db.commit()
    slice_data = SessionSlice(
        section_ids=[section.id],
        sections=[{"id": section.id, "title": section.title}],
        total_tokens=100,
        total_reading_time=10,
        chunk_ids=[chunk.id for chunk in chunks],
        context_text="Selected reading context",
    )
    with (
        patch("app.discussion.engine.get_llm_client", return_value=llm),
        patch("app.discussion.engine.get_fast_llm_client", return_value=llm),
    ):
        engine = DiscussionEngine(mock_db, session, slice_data)
    return engine, session


def search_patch(chunk):
    return patch(
        "app.discussion.agents.search_chunks",
        new_callable=AsyncMock,
        return_value=[
            SearchResult(
                chunk_id=chunk.id,
                section_id=chunk.section_id,
                section_title="Chapter 1",
                text=chunk.text,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                source_ref=None,
                score=1.0,
            )
        ],
    )


def collect_stream(engine, content="What does the opening image do?") -> list[dict]:
    async def _collect():
        events = []
        async for event in engine.stream_user_message(
            content, include_close_reader=False, adaptive=False
        ):
            events.append(event)
        return events

    return asyncio.run(_collect())


def events_of(events: list[dict], event_type: str) -> list[dict]:
    return [event for event in events if event["type"] == event_type]


def test_validated_stream_never_leaks_raw_json_or_rejected_claims(
    mock_db, sample_book
):
    chunk = sample_book["chunks"][0]
    llm = StructuredStub(
        grounded_payload(chunk.id, include_unsupported=True),
        grounded_payload(chunk.id, include_unsupported=True),
    )
    engine, _ = build_engine(mock_db, sample_book, llm)

    with search_patch(chunk):
        events = collect_stream(engine)

    assert len(llm.calls) == 2  # initial + exactly one repair

    deltas = [event["delta"] for event in events_of(events, "message_delta")]
    sentences = [event["sentence"] for event in events_of(events, "sentence_ready")]
    assert deltas and sentences
    for text in deltas + sentences:
        assert "{" not in text and '"segments"' not in text
        assert REJECTED_MARKER not in text

    message_end = events_of(events, "message_end")[0]
    assert REJECTED_MARKER not in message_end["content"]
    assert "".join(deltas) == message_end["content"]
    assert [segment["id"] for segment in message_end["segments"]] == [
        "claim",
        "question",
    ]
    assert message_end["grounding"]["repair_attempted"] is True
    assert message_end["grounding"]["metrics"]["dropped_segments"] == 1


def test_message_end_matches_persisted_grounded_message(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    llm = StructuredStub(grounded_payload(chunk.id))
    engine, session = build_engine(mock_db, sample_book, llm)

    with search_patch(chunk):
        events = collect_stream(engine)

    message_end = events_of(events, "message_end")[0]

    rows = (
        mock_db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.created_at)
        .all()
    )
    assert [row.role for row in rows] == [MessageRole.USER, MessageRole.FACILITATOR]
    agent_row = rows[1]

    assert message_end["message_id"] == agent_row.id
    assert message_end["content"] == agent_row.content
    assert message_end["citations"] == agent_row.citations
    assert (
        message_end["segments"]
        == agent_row.metadata_json["grounded_response"]["segments"]
    )

    citation = message_end["citations"][0]
    assert citation["citation_id"] == "evidence"
    assert citation["segment_ids"] == ["claim"]
    assert citation["verified"] is True
    segment_citation_ids = {
        citation_id
        for segment in message_end["segments"]
        for citation_id in segment["citation_ids"]
    }
    assert segment_citation_ids == {"evidence"}


def test_streaming_and_nonstreaming_grounded_parity(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    content = "What does the opening image do?"

    stream_llm = StructuredStub(grounded_payload(chunk.id))
    stream_engine, stream_session = build_engine(mock_db, sample_book, stream_llm)
    with search_patch(chunk):
        events = collect_stream(stream_engine, content)
    message_end = events_of(events, "message_end")[0]

    batch_llm = StructuredStub(grounded_payload(chunk.id))
    batch_engine, batch_session = build_engine(mock_db, sample_book, batch_llm)
    with search_patch(chunk):
        responses = asyncio.run(
            batch_engine.process_user_message(
                content, include_close_reader=False, adaptive=False
            )
        )
    batch_response = responses[0]

    assert message_end["content"] == batch_response.content
    assert message_end["segments"] == batch_response.segments
    assert message_end["grounding"] == batch_response.grounding_metadata
    assert message_end["citations"] == DiscussionEngine._serialize_citations(
        batch_response.citations
    )
    assert message_end["token_usage"]["total_tokens"] == (
        batch_response.input_tokens + batch_response.output_tokens
    )

    def facilitator_row(session_id):
        rows = (
            mock_db.query(Message)
            .filter(
                Message.session_id == session_id,
                Message.role == MessageRole.FACILITATOR,
            )
            .all()
        )
        assert len(rows) == 1
        return rows[0]

    stream_row = facilitator_row(stream_session.id)
    batch_row = facilitator_row(batch_session.id)
    assert stream_row.content == batch_row.content
    assert stream_row.citations == batch_row.citations
    assert stream_row.metadata_json == batch_row.metadata_json
