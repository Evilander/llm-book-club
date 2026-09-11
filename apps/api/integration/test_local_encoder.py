"""Opt-in real CPU encoder + Postgres path; no hosted model credentials."""
import os

import pytest
from sqlalchemy.orm import Session

from app.db import init_db as bootstrap
from app.db.models import DiscussionSession, Message, MessageRole
from app.providers.embeddings.space import LOCAL_MODEL, LOCAL_REVISION, configured_space
from app.services.book_recall import recall_for_turn
from app.services.search_index import refresh_book_index, index_counts
from app.retrieval.search import vector_search
from app.settings import settings
from .test_database import seed_book


@pytest.mark.skipif(not os.environ.get("LOCAL_ENCODER_TEST_CACHE"), reason="Set LOCAL_ENCODER_TEST_CACHE to run the real pinned CPU model.")
@pytest.mark.asyncio
async def test_local_model_indexes_and_recalls_an_older_paraphrased_thought(pg_engine, monkeypatch):
    bootstrap.init_db()
    seed_book(pg_engine)
    monkeypatch.setattr(settings, "embeddings_provider", "local")
    monkeypatch.setattr(settings, "local_embeddings_base_url", None)
    monkeypatch.setattr(settings, "local_embeddings_model", LOCAL_MODEL)
    monkeypatch.setattr(settings, "local_embeddings_revision", LOCAL_REVISION)
    monkeypatch.setattr(settings, "local_embeddings_dimension", 1024)
    monkeypatch.setattr(settings, "local_embeddings_cache_dir", os.environ["LOCAL_ENCODER_TEST_CACHE"])
    with Session(pg_engine) as db:
        old = DiscussionSession(book_id="book", section_ids=["read"])
        current = DiscussionSession(book_id="book", section_ids=["read"])
        db.add_all([old, current]); db.flush()
        target = "I felt the locked door was about her fear of remembering childhood."
        memories = [target, "I liked the rhythm of that poem.", "The bakery sounds delightful.", "The town has an unusual name.", "I wonder how they built the bridge.", "The mayor seems very tired.", "I liked the joke about the dog.", "I noticed the river was low."]
        db.add_all([Message(session_id=old.id, role=MessageRole.USER, content=content) for content in memories])
        db.commit()
        await refresh_book_index(db, "book", configured_space().id)
        assert index_counts(db, "book")["ready"]
        query = "How did I interpret that inaccessible room and her suppressed past?"
        new = Message(session_id=current.id, role=MessageRole.USER, content=query)
        db.add(new); db.commit()
        recalled = await recall_for_turn(db, "book", ["read"], query, {new.id}, reader_message=new)
        assert target in recalled and query not in recalled
        assert db.get(Message, new.id).embedding_space == configured_space().id
        found = await vector_search(db, "book", "Who discovered the navigation instrument?", section_ids=["read"])
        assert [item.chunk_id for item in found] == ["read"]
