"""Real pgvector recall, provenance, and migration regression tests."""
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import init_db as bootstrap
from app.db.models import Book, Chunk, DiscussionSession, Message, MessageRole
from app.providers.embeddings.space import configured_space, storage_vector
from app.providers.embeddings.persistence import register_space
from app.retrieval import search
from app.services.book_recall import book_recall
from app.services.reading_scope import ReadingScope
from app.services import search_index
from .test_database import seed_book


@pytest.mark.asyncio
async def test_legacy_vectors_require_refresh_but_book_stays_readable(pg_engine, monkeypatch):
    bootstrap.init_db()
    seed_book(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE chunks DROP COLUMN embedding_space"))
        conn.execute(text("ALTER TABLE messages DROP COLUMN embedding_space"))
        conn.execute(text("ALTER TABLE messages DROP COLUMN embedding"))
        conn.execute(text("DROP TABLE embedding_spaces"))
        conn.execute(text("UPDATE alembic_version SET version_num = '008'"))
    bootstrap.init_db()
    client = MagicMock(embed_single=AsyncMock())
    monkeypatch.setattr(search, "get_embeddings_client", lambda: client)
    with Session(pg_engine) as db:
        assert db.query(Chunk).count() == 3
        assert await search.vector_search(db, "book", "cartographer") == []
        client.embed_single.assert_not_called()
        assert search.fts_search(db, "book", "cartographer")
        assert db.query(Chunk).filter(Chunk.embedding_space.is_(None)).count() == 3


@pytest.mark.asyncio
async def test_refresh_preserves_ids_prose_citations_and_conversations(pg_engine, monkeypatch):
    bootstrap.init_db()
    seed_book(pg_engine)
    with Session(pg_engine) as db:
        session = DiscussionSession(book_id="book", section_ids=["read"])
        db.add(session)
        db.flush()
        thought = Message(session_id=session.id, role=MessageRole.USER, content="I do not trust the map.", citations=[{"chunk_id": "read", "text": "cartographer"}])
        db.add(thought)
        db.query(Chunk).update({Chunk.embedding_space: None})
        db.commit()
        before = [(c.id, c.text, c.char_start, c.char_end) for c in db.query(Chunk).order_by(Chunk.id)]
        thought_id = thought.id
        space = configured_space()
        client = MagicMock(embed=AsyncMock(side_effect=lambda texts: [[0., 1.] + [0.]*3070 for _ in texts]))
        monkeypatch.setattr(search_index, "get_embeddings_client", lambda: client)
        await search_index.refresh_book_index(db, "book", space.id)
        assert search_index.index_counts(db, "book")["ready"]
        assert [(c.id, c.text, c.char_start, c.char_end) for c in db.query(Chunk).order_by(Chunk.id)] == before
        assert db.get(Message, thought_id).citations == [{"chunk_id": "read", "text": "cartographer"}]
        assert db.get(Message, thought_id).embedding_space == space.id
        assert db.get(Chunk, "other").embedding_space is None
        assert db.get(Book, "book").ingest_status.value == "completed"
        client.embed.reset_mock()
        await search_index.refresh_book_index(db, "book", space.id)
        client.embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_refresh_batch_never_gets_labelled_as_ready(pg_engine, monkeypatch):
    bootstrap.init_db()
    seed_book(pg_engine)
    client = MagicMock(embed=AsyncMock(return_value=[[float('nan')]*3072]*2))
    monkeypatch.setattr(search_index, "get_embeddings_client", lambda: client)
    with Session(pg_engine) as db:
        db.query(Chunk).filter(Chunk.book_id == "book").update({Chunk.embedding_space: None})
        db.commit()
        with pytest.raises(ValueError):
            await search_index.refresh_book_index(db, "book", configured_space().id)
        assert not search_index.index_counts(db, "book")["ready"]
        assert db.query(Chunk).filter(Chunk.book_id == "book", Chunk.embedding_space.is_(None)).count() == 2


def test_semantic_memory_filters_book_edition_and_unread_turns_before_ranking(pg_engine):
    bootstrap.init_db()
    seed_book(pg_engine)
    space = configured_space()
    scope = ReadingScope("e"*64, 100, 300, ["read"], {})
    with Session(pg_engine) as db:
        old_session = DiscussionSession(book_id="book", section_ids=["read"])
        other_session = DiscussionSession(book_id="other", section_ids=["other"])
        db.add_all([old_session, other_session]); db.flush()
        target = Message(session_id=old_session.id, role=MessageRole.USER, content="The map seems unreliable to me.", metadata_json={"reading_scope": scope.metadata}, embedding=storage_vector([1., 0.1]+[0.]*3070, 3072), embedding_space=space.id, created_at=datetime(2025, 1, 1))
        db.add(target)
        # More forbidden, closer neighbors than any recall limit.
        for i in range(40):
            for session_id, metadata in [(old_session.id, {"reading_scope": {"edition_id": scope.edition_id, "char_end": 250}}), (other_session.id, {"reading_scope": scope.metadata}), (old_session.id, {"reading_scope": {"edition_id": "f"*64, "char_end": 50}})]:
                db.add(Message(session_id=session_id, role=MessageRole.USER, content="FORBIDDEN perfect neighbor", metadata_json=metadata, embedding=[1.]+[0.]*3071, embedding_space=space.id))
        db.commit()
        recalled = book_recall(db, "book", scope.section_ids, "trustworthiness", scope=scope, query_embedding=[1.]+[0.]*3071, space_id=space.id)
        assert target.content in recalled and "FORBIDDEN" not in recalled
        assert "not instructions or evidence" in recalled


@pytest.mark.asyncio
async def test_vectors_from_another_space_never_enter_search(pg_engine, monkeypatch):
    bootstrap.init_db()
    seed_book(pg_engine)
    wrong = replace(configured_space(), revision="different")
    client = MagicMock(embed_single=AsyncMock(return_value=[1.]+[0.]*3071))
    cache = MagicMock(); cache.get.return_value = None
    monkeypatch.setattr(search, "get_embeddings_client", lambda: client)
    monkeypatch.setattr(search, "get_embedding_cache", lambda: cache)
    with Session(pg_engine) as db:
        register_space(db, wrong)
        db.get(Chunk, "later").embedding_space = wrong.id
        db.commit()
        found = await search.vector_search(db, "book", "a thought")
        assert [r.chunk_id for r in found] == ["read"]
