"""Refresh derived vectors in bounded batches, preserving all reader records."""
import asyncio

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from ..db.models import Book, Chunk, DiscussionSession, IngestStatus, Message, MessageRole, Section
from ..providers.embeddings.factory import get_embeddings_client
from ..providers.embeddings.persistence import register_space
from ..providers.embeddings.space import configured_space, storage_batch


def _needs_index(model, space_id):
    return or_(model.embedding_space.is_(None), model.embedding_space != space_id, model.embedding.is_(None))


def index_counts(db: Session, book_id: str) -> dict:
    space = configured_space()
    chunks = db.query(Chunk).filter(Chunk.book_id == book_id)
    thoughts = db.query(Message).join(DiscussionSession).filter(DiscussionSession.book_id == book_id, Message.role == MessageRole.USER, func.trim(Message.content) != "")
    total = chunks.count()
    pending = chunks.filter(_needs_index(Chunk, space.id)).count()
    memory_total = thoughts.count()
    memory_pending = thoughts.filter(_needs_index(Message, space.id)).count()
    return {"space_id": space.id, "local": space.provider == "local", "passages": total, "passages_ready": total - pending, "thoughts": memory_total, "thoughts_ready": memory_total - memory_pending, "ready": total > 0 and pending == 0 and memory_pending == 0}


async def refresh_book_index(db: Session, book_id: str, space_id: str) -> None:
    space = configured_space()
    if space.id != space_id:
        raise ValueError("The search configuration changed. Start the refresh again.")
    book = db.get(Book, book_id)
    if book is None or book.ingest_status != IngestStatus.COMPLETED:
        return
    client = get_embeddings_client()
    for model in (Chunk, Message):
        while True:
            if model is Chunk:
                rows = db.query(Chunk, Section).join(Section).filter(Chunk.book_id == book_id, _needs_index(Chunk, space.id)).order_by(Chunk.id).limit(32).all()
                records = [chunk for chunk, _ in rows]
                texts = [f"[Book: {book.title} | Section {section.order_index + 1}: {section.title or ''}] {chunk.text}" for chunk, section in rows]
            else:
                records = db.query(Message).join(DiscussionSession).filter(DiscussionSession.book_id == book_id, Message.role == MessageRole.USER, func.trim(Message.content) != "", _needs_index(Message, space.id)).order_by(Message.id).limit(32).all()
                texts = [message.content for message in records]
            if not records:
                break
            # No replacement of chunks/sessions and no ingest status changes.
            # Only fully validated batches become visible in the new space.
            vectors = storage_batch(await client.embed(texts), len(records), space.dimension)
            register_space(db, space)
            for record, vector in zip(records, vectors):
                record.embedding = vector
                record.embedding_space = space.id
            db.commit()


def run_index_refresh(book_id: str, space_id: str) -> str:
    from ..db.engine import SessionLocal
    with SessionLocal() as db:
        asyncio.run(refresh_book_index(db, book_id, space_id))
    return "ready"
