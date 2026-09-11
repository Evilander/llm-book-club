"""Reading boundaries survive page turns, session reuse, and library re-imports."""
import json
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest

from app.db.models import Message, MessageRole
from app.discussion.agents import verify_citations
from app.services.book_recall import book_recall
from app.services.reading_scope import ReaderPosition, build_scope, load_reading, session_scope
from tests.test_library import integration_engine, integration_db, client, populated_book  # noqa: F401


def test_citation_text_is_the_exact_original_span(mock_db, sample_book):
    source = sample_book["chunks"][0]
    source.text = "🌿 Cafe\u0301\u2003  waited at the gate."
    mock_db.commit()
    verified, invalid = verify_citations(mock_db, [{"chunk_id": source.id, "text": "CAFÉ waited"}])
    assert not invalid
    citation = verified[0]
    assert citation["text"] == source.text[citation["char_start"]:citation["char_end"]]
    assert citation["text"] == "Cafe\u0301\u2003  waited"


def test_quote_cannot_cross_the_current_page_or_use_fake_offsets(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    chunk.text = "The lamp was lit. The final visitor was a ghost."
    mock_db.commit()
    bounds = {chunk.id: (0, len("The lamp was lit."))}
    for citation in [
        {"text": "The final visitor was a ghost."},
        {"text": "lit. The final visitor"},
        {"text": "The lamp was lit.", "char_start": 1, "char_end": 10},
        {"text": "The lamp was lit.", "char_start": False, "char_end": 17},
        {"text": "The lamp was lit.", "char_start": -1, "char_end": 17},
    ]:
        verified, invalid = verify_citations(mock_db, [{"chunk_id": chunk.id, "verified": True, **citation}], allowed_spans=bounds)
        assert not verified and len(invalid) == 1
    verified, invalid = verify_citations(mock_db, [{"chunk_id": chunk.id, "text": "The lamp was lit."}], allowed_spans=bounds)
    assert not invalid and verified[0]["char_end"] == bounds[chunk.id][1]
    assert not verify_citations(mock_db, [{"chunk_id": chunk.id, "text": "lamp"}], allowed_chunk_ids=[])[0]


@pytest.mark.parametrize("bad", [None, [], {"chunk_id": []}, {"chunk_id": "x", "text": {"quote": "invented"}}])
def test_malformed_citation_is_not_coerced_to_a_valid_quote(mock_db, bad):
    verified, invalid = verify_citations(mock_db, [bad])
    assert not verified and len(invalid) == 1


def test_boundary_cannot_verify_part_of_a_grapheme(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    chunk.text = "abc e\u0301 further words"
    mock_db.commit()
    verified, invalid = verify_citations(mock_db, [{"chunk_id": chunk.id, "text": "abc e"}], allowed_spans={chunk.id: (0, 5)})
    assert not verified and invalid


def test_history_citations_use_one_query_and_keep_message_markers(mock_db, sample_book):
    from sqlalchemy import event
    from app.discussion.agents import verify_citation_groups
    chunk = sample_book["chunks"][0]
    quote = chunk.text[:40]
    groups = [
        [{"chunk_id": chunk.id, "text": quote, "marker": 1}],
        [{"chunk_id": chunk.id, "text": "AN INVENTED QUOTATION", "verified": True, "match_type": "fuzzy"}],
        [{"chunk_id": chunk.id, "text": quote, "marker": 4}],
        [],
    ]
    statements = []
    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)
    event.listen(mock_db.bind, "before_cursor_execute", record)
    try:
        checked = verify_citation_groups(mock_db, groups)
    finally:
        event.remove(mock_db.bind, "before_cursor_execute", record)
    assert len(statements) == 1
    assert checked[0][0][0]["marker"] == 1
    assert not checked[1][0] and checked[1][1]
    assert checked[2][0][0]["marker"] == 4
    assert checked[3] == ([], [])


def test_initial_and_retrieved_text_share_one_evidence_budget(mock_db, sample_book):
    from app.discussion.agents import FacilitatorAgent
    from app.retrieval.search import SearchResult
    from app.settings import settings
    reading, _ = load_reading(mock_db, sample_book["book"].id)
    with patch.object(settings, "max_context_tokens", 50):
        scope = build_scope(reading, section_ids=[sample_book["section"].id])
        agent = FacilitatorAgent(None, mock_db, sample_book["book"].id, "", initial_evidence=scope.initial_evidence)
        oversized = SearchResult("extra", "section", "Chapter", "x" * 1000, 0, 1000, None, 1.0)
        assert agent._build_retrieval_context([oversized])
        assert sum(len(c["text"]) for c in agent._last_retrieved_chunks) <= 200
        assert len(oversized.text) == 1000
        agent._initial_evidence = [{"chunk_id": "full", "text": "x" * 200}]
        assert agent._build_retrieval_context([oversized]) == ""
        assert agent._last_retrieved_chunks == agent._initial_evidence


def test_old_thoughts_survive_same_session_moving_forward_and_back(mock_db, sample_book, sample_session):
    reading, _ = load_reading(mock_db, sample_book["book"].id)
    early = build_scope(reading, position=ReaderPosition(page=1, page_size=200))
    later = build_scope(reading, section_ids=sample_session.section_ids)
    assert early.char_end < later.char_end
    mock_db.add_all([
        Message(session_id=sample_session.id, role=MessageRole.USER, content="The courtyard feels like a waiting room.", metadata_json={"reading_scope": early.metadata}),
        Message(session_id=sample_session.id, role=MessageRole.USER, content="LATER REVELATION in the courtyard.", metadata_json={"reading_scope": later.metadata}),
        Message(session_id=sample_session.id, role=MessageRole.USER, content="LEGACY UNKNOWN BOUNDARY"),
    ])
    mock_db.commit()
    recall = book_recall(mock_db, sample_book["book"].id, early.section_ids, "courtyard", scope=early)
    assert "waiting room" in recall
    assert "LATER REVELATION" not in recall and "LEGACY UNKNOWN" not in recall
    recall = book_recall(mock_db, sample_book["book"].id, later.section_ids, "courtyard", scope=later)
    assert "waiting room" in recall and "LATER REVELATION" in recall
    assert mock_db.query(Message).filter_by(session_id=sample_session.id).count() == 3


def test_changed_edition_rejects_stale_position(mock_db, sample_book, sample_session):
    reading, _ = load_reading(mock_db, sample_book["book"].id)
    before = build_scope(reading, position=ReaderPosition(page=1, page_size=200))
    sample_book["chunks"][0].text = "A revised opening. " * 30
    sample_session.preferences_json = {"reading_companion": True, "reading_position": before.position}
    mock_db.commit()
    with pytest.raises(ValueError, match="book has changed"):
        session_scope(mock_db, sample_session)


def test_book_changed_between_displaying_page_and_opening_companion(client, populated_book, integration_db):
    from app.db.models import Chunk
    reader = client.get(f"/v1/books/{populated_book.id}/reader", params={"page_size": 200}).json()
    assert len(reader["edition_id"]) == 64
    source = integration_db.query(Chunk).filter_by(book_id=populated_book.id).first()
    source.text = source.text.replace("The", "A", 1) + " Revised text."
    integration_db.commit()
    response = client.post(f"/v1/books/{populated_book.id}/companion", json={
        "page": reader["page"], "page_size": reader["page_size"], "edition_id": reader["edition_id"],
        "section_ids": list({span["section_id"] for span in reader["chunks"]}),
    })
    assert response.status_code == 409, response.text
    assert "book has changed" in response.json()["detail"]


def test_two_tabs_pin_turn_context_and_filter_visible_history(client, populated_book, integration_db):
    from app.db.models import Chunk, Section
    source = integration_db.query(Chunk).filter_by(book_id=populated_book.id).first()
    source.text = "The lamp was lit before dawn. " * 30 + "UNREAD_FINAL_REVELATION"
    source.char_end = len(source.text)
    integration_db.commit()
    path = f"/v1/books/{populated_book.id}/companion"
    first = client.post(path, json={"section_ids": [source.section_id], "page": 1, "page_size": 200}).json()
    later = client.post(path, json={"section_ids": [source.section_id], "page": 4, "page_size": 200}).json()
    assert first["session_id"] == later["session_id"]
    prompts = []

    class Provider:
        last_stream_usage = None
        async def stream(self, messages, **kwargs):
            prompts.append(messages)
            response = json.dumps({"analysis": "The lamp gives us a place to begin [1]. What do you notice?", "citations": [{"marker": 1, "chunk_id": source.id, "quote": "The lamp was lit before dawn."}]})
            for start in range(0, len(response), 7):
                yield response[start:start + 7]

    endpoint = f"/v1/sessions/{first['session_id']}"
    with patch("app.discussion.engine.get_llm_client", return_value=Provider()), patch("app.discussion.agents.search_chunks", new=AsyncMock(return_value=[])):
        for opened, thought in [(later, "LATER_TAB_THOUGHT"), (first, "EARLY_TAB_THOUGHT")]:
            response = client.post(endpoint + "/message/stream", json={"content": thought, "reading_position": opened["reading_position"], "include_close_reader": False, "adaptive": False})
            assert response.status_code == 200, response.text
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            final = next(e for e in events if e['type'] == 'message_end')
            assert final['citations'][0]['verified']
            visible = ''.join(e['delta'] for e in events if e['type'] == 'message_delta')
            assert visible == final['content']
            assert all('"analysis"' not in e.get('sentence', '') for e in events)
    early_prompt = '\n'.join(message.content for message in prompts[-1])
    assert "EARLY_TAB_THOUGHT" in early_prompt
    assert "LATER_TAB_THOUGHT" not in early_prompt and "UNREAD_FINAL_REVELATION" not in early_prompt
    # The later tab remains on its own page; the earlier request did not move it.
    history = client.get(endpoint + "/messages", params=first['reading_position']).json()['messages']
    assert any(m['content'] == 'EARLY_TAB_THOUGHT' for m in history)
    assert not any(m['content'] == 'LATER_TAB_THOUGHT' for m in history)
    history = client.get(endpoint + "/messages", params=later['reading_position']).json()['messages']
    assert any(m['content'] == 'LATER_TAB_THOUGHT' for m in history)


@pytest.mark.asyncio
async def test_reranker_and_evidence_receive_only_the_read_prefix(mock_db):
    from app.retrieval import search
    source = search.SearchResult('chunk', 'chapter', 'Chapter', 'Read prefix. UNREAD SECRET', 0, 26, None, 1.0)
    reranker = SimpleNamespace(rerank=AsyncMock(return_value=[SimpleNamespace(index=0, score=1.0)]))
    with patch.object(search, 'vector_search', new=AsyncMock(return_value=[source])) as vector, patch.object(search, 'fts_search', return_value=[source]), patch.object(search, 'get_reranker_client', return_value=reranker):
        results = await search.hybrid_search(mock_db, 'book', 'query', allowed_spans={'chunk': (0, 12)})
    assert vector.call_args.kwargs['chunk_ids'] == ['chunk']
    assert reranker.rerank.call_args.kwargs['documents'] == ['Read prefix.']
    assert results[0].text == 'Read prefix.'


@pytest.mark.asyncio
async def test_failed_repair_withholds_the_bad_quotation(mock_db, sample_book):
    from app.discussion.agents import FacilitatorAgent
    chunk = sample_book['chunks'][0]
    provider = SimpleNamespace(complete=AsyncMock(return_value=json.dumps({'analysis': 'Invented claim [1]', 'citations': [{'marker': 1, 'chunk_id': chunk.id, 'quote': 'fabricated quotation'}]})))
    agent = FacilitatorAgent(provider, mock_db, sample_book['book'].id, 'Read together', allowed_chunk_ids=[chunk.id], initial_evidence=[{'chunk_id': chunk.id, 'text': chunk.text}])
    content, citations, metrics = await agent._verify_and_maybe_repair('bad reply', 'Invented claim', [{'chunk_id': chunk.id, 'text': 'fabricated quotation'}])
    assert 'Invented' not in content and 'fabricated' not in content
    assert not citations and metrics.repair_attempted and not metrics.repair_succeeded
    assert provider.complete.await_count == 1
    messages = provider.complete.call_args.args[0]
    assert messages[0].role == 'system' and 'untrusted' in messages[0].content
