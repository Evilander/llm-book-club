"""No lost words, real margin quotes, and bounded, persistent book recall."""
import json
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from app.db.models import Chunk, DiscussionSession, Message, MessageRole, Section
from app.services.reader_text import assemble_reading_text, page_bounds
from app.services.book_recall import book_recall
from app.retrieval.selector import select_session_slice
from app.routers.companion import verified_page_notes
from tests.test_library import integration_engine, integration_db, client, populated_book  # noqa: F401


def chunk(text, start, identifier="c"):
    return SimpleNamespace(id=identifier, section_id="s", text=text, char_start=start, char_end=start + len(text))


@pytest.mark.parametrize("overlap", [1, 7, 38, 120, 199])
def test_reading_edition_removes_short_and_long_overlaps(overlap):
    text = " ".join(f"word{i}" for i in range(120))
    chunks = [chunk(text[:300], 0), chunk(text[300-overlap:600], 300-overlap, "c2")]
    reading = assemble_reading_text(chunks)
    assert reading.text == text[:600]
    for source, span in zip(chunks, reading.chunks):
        assert reading.text[span["char_start"]:span["char_end"]] == source.text


def test_legacy_stripped_offsets_do_not_shift_quotes():
    text = "\n  The orchard was still. Beyond it the road bent into the hills."
    chunks = [chunk(text[:45].strip(), 0), chunk(text[22:].strip(), 22, "c2")]
    chunks[0].char_end = 45
    reading = assemble_reading_text(chunks)
    assert reading.text == text.strip()
    assert reading.text[reading.chunks[1]["char_start"]:] == chunks[1].text


@pytest.mark.parametrize("page_size", [13, 41, 400, 1800])
def test_page_boundaries_are_contiguous_and_lossless(page_size):
    text = ("🌿 Céline lingered at the door.\n\nNothing had changed, and yet everything had. " * 90).strip()
    bounds = [page_bounds(text, page, page_size) for page in range(1, math.ceil(len(text)/page_size)+1)]
    assert "".join(text[start:end] for start, end in bounds) == text
    assert all(bounds[i][1] == bounds[i+1][0] for i in range(len(bounds)-1))


def test_notes_require_exact_on_page_quotes_and_ignore_model_chunk_ids():
    source = chunk("🌿 The garden remembered the rain. No one had opened the gate.", 0)
    reading = assemble_reading_text([source])
    payload = {"notes": [{"chunk_id": "made-up", "quote": "The garden remembered the rain.", "question": "What does it mean for a place to remember?"}, {"quote": "The garden forgot the rain.", "question": "Why did it forget?"}]}
    notes = verified_page_notes(json.dumps(payload), reading, 0, len(reading.text), [source])
    assert len(notes) == 1
    assert notes[0]["chunk_id"] == "c" and notes[0]["char_start"] == 2
    assert reading.text[notes[0]["char_start"]:notes[0]["char_end"]] == notes[0]["quote"]
    assert verified_page_notes(json.dumps(payload), reading, 40, len(reading.text), [source]) == []


@pytest.mark.parametrize("raw", ['oops', '[]', '{"notes": 5}', '{"notes":[null, {"quote": 8}]}'])
def test_malformed_notes_never_become_highlights(raw):
    assert verified_page_notes(raw, assemble_reading_text([]), 0, 0, []) == []


def test_reader_and_citation_location_share_coordinates(client, populated_book, integration_db):
    section = integration_db.query(Section).filter_by(book_id=populated_book.id).first()
    integration_db.query(Chunk).filter_by(book_id=populated_book.id).delete()
    text = "🌿 " + " ".join(f"word{i}" for i in range(900))
    sources = []
    for i, start in enumerate(range(0, len(text), 700)):
        source = Chunk(book_id=populated_book.id, section_id=section.id, order_index=i, text=text[start:start+850], char_start=start, char_end=min(start+850, len(text)))
        integration_db.add(source); sources.append(source)
    integration_db.commit()
    first = client.get(f"/v1/books/{populated_book.id}/reader?page_size=400").json()
    pages = [first] + [client.get(f"/v1/books/{populated_book.id}/reader?page={i}&page_size=400").json() for i in range(2, first["total_pages"]+1)]
    assert "".join(page["text"] for page in pages) == text
    for offset in [0, 99, 100, 499, len(sources[1].text)-1]:
        res = client.get(f"/v1/books/{populated_book.id}/reader-location", params={"chunk_id": sources[1].id, "char_start": offset, "page_size": 400})
        assert res.status_code == 200, res.text
        location = res.json(); page = pages[location["page"]-1]
        assert page["char_start"] <= location["char_start"] < page["char_end"]
        assert text[location["char_start"]] == sources[1].text[offset]
    assert client.get(f"/v1/books/{populated_book.id}/reader-location?chunk_id=missing").status_code == 404


def test_companion_reuses_session_across_chapters_and_saves_page(client, populated_book, integration_db):
    first = integration_db.query(Section).filter_by(book_id=populated_book.id).first()
    second = Section(book_id=populated_book.id, title="Chapter 2", order_index=1, section_type="chapter", char_start=251, char_end=500)
    integration_db.add(second); integration_db.commit()
    path = f"/v1/books/{populated_book.id}/companion"
    opened = client.post(path, json={"section_ids": [first.id], "page": 1}).json()
    next_chapter = client.post(path, json={"section_ids": [second.id]}).json()
    assert opened["session_id"] == next_chapter["session_id"]
    saved = integration_db.get(DiscussionSession, opened["session_id"])
    assert set(saved.section_ids) == {first.id, second.id}
    assert saved.preferences_json["current_page_text"].startswith("Moonlight")
    assert client.post(path, json={"section_ids": [second.id], "page": 1}).status_code == 400
    assert client.post(path, json={"section_ids": ["other-book-section"]}).status_code == 400


def test_margin_questions_are_cached_and_hidden_from_conversation(client, populated_book, integration_db):
    section = integration_db.query(Section).filter_by(book_id=populated_book.id).first()
    session = client.post(f"/v1/books/{populated_book.id}/companion", json={"section_ids": [section.id], "page": 1}).json()["session_id"]
    llm = SimpleNamespace(complete=AsyncMock(return_value=json.dumps({"notes": [{"quote": "Moonlight pressed against the glass", "question": "What does this light make you feel?"}]})))
    with patch("app.routers.companion.get_llm_client", return_value=llm):
        first = client.post(f"/v1/books/{populated_book.id}/reader-notes", json={"session_id": session, "page": 1})
        second = client.post(f"/v1/books/{populated_book.id}/reader-notes", json={"session_id": session, "page": 1})
    assert first.status_code == 200, first.text
    assert len(first.json()["notes"]) == 1 and first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["notes"] == second.json()["notes"]
    assert llm.complete.await_count == 1
    assert client.get(f"/v1/sessions/{session}/messages").json()["messages"] == []


def test_companion_rotates_at_limit_without_discarding_memory(client, populated_book, integration_db):
    from app.settings import settings
    section = integration_db.query(Section).filter_by(book_id=populated_book.id).first()
    payload = {"section_ids": [section.id]}; path = f"/v1/books/{populated_book.id}/companion"
    first = client.post(path, json=payload).json()["session_id"]
    integration_db.add(Message(session_id=first, role=MessageRole.USER, content="I think the archive is a place of memory."))
    integration_db.add(Message(session_id=first, role=MessageRole.SYSTEM, content="", metadata_json={"reader_notes_key": "cache"}))
    integration_db.commit()
    with patch.object(settings, "max_session_messages", 2):
        assert client.post(path, json=payload).json()["session_id"] == first
    with patch.object(settings, "max_session_messages", 1):
        second = client.post(path, json=payload).json()["session_id"]
    assert second != first and integration_db.get(DiscussionSession, first).is_active is False
    assert "place of memory" in book_recall(integration_db, populated_book.id, [section.id], "archive")


def test_recall_stays_in_book_and_before_current_chapter(mock_db, sample_book, sample_session):
    section = sample_book["section"]
    later = Section(book_id=sample_book["book"].id, title="Later", order_index=5, section_type="chapter", char_start=600, char_end=700)
    mock_db.add(later); mock_db.flush()
    future = DiscussionSession(book_id=sample_book["book"].id, section_ids=[later.id])
    other = DiscussionSession(book_id="another-book", section_ids=[section.id])
    mock_db.add_all([future, other]); mock_db.flush()
    mock_db.add_all([Message(session_id=sample_session.id, role=MessageRole.USER, content="The courtyard feels lonely."), Message(session_id=future.id, role=MessageRole.USER, content="FUTURE SPOILER"), Message(session_id=other.id, role=MessageRole.USER, content="OTHER BOOK PRIVATE"), Message(session_id=sample_session.id, role=MessageRole.FACILITATOR, content="UNCHECKED MODEL CLAIM")])
    mock_db.commit()
    recalled = book_recall(mock_db, sample_book["book"].id, [section.id], "courtyard")
    assert "courtyard feels lonely" in recalled
    assert all(excluded not in recalled for excluded in ["FUTURE SPOILER", "OTHER BOOK PRIVATE", "UNCHECKED MODEL CLAIM"])
    assert "untrusted conversation memory" in recalled


def test_intro_context_is_bounded_but_retrieval_keeps_full_slice(mock_db, sample_book):
    from app.settings import settings
    with patch.object(settings, "max_context_tokens", 30):
        selected = select_session_slice(mock_db, sample_book["book"].id, section_ids=[sample_book["section"].id])
    assert len(selected.context_text) <= 120 and len(selected.chunk_ids) == 5
