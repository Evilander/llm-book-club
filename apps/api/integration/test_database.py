from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock

from alembic import command
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db import init_db as bootstrap
from app.db.models import Base, Book, Chunk, IngestStatus, Section
from app.retrieval import search


def seed_book(engine):
    with Session(engine) as db:
        db.add_all([
            Book(id="book", title="Fixture book", filename="fixture.txt", file_type="txt", file_size_bytes=10, ingest_status=IngestStatus.COMPLETED),
            Book(id="other", title="Other fixture", filename="other.txt", file_type="txt", file_size_bytes=10, ingest_status=IngestStatus.COMPLETED),
        ])
        db.flush()
        for i, (section_id, book_id) in enumerate([("read", "book"), ("later", "book"), ("other", "other")]):
            db.add(Section(id=section_id, book_id=book_id, title=section_id, section_type="chapter", order_index=i, char_start=i*100, char_end=(i+1)*100))
        db.flush()
        for i, (section_id, book_id) in enumerate([("read", "book"), ("later", "book"), ("other", "other")]):
            db.add(Chunk(id=section_id, book_id=book_id, section_id=section_id, order_index=0,
                         text="The cartographer found an amber compass.", char_start=i*100, char_end=(i+1)*100,
                         embedding=[1.0] + [0.0] * 3071))
        db.commit()


def test_fresh_bootstrap_and_repeated_start_keep_data(pg_engine):
    bootstrap.init_db()
    seed_book(pg_engine)
    bootstrap.init_db()
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "007"
        assert connection.execute(text("SELECT count(*) FROM books")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM chunks WHERE text_search @@ plainto_tsquery('english', 'cartographer')")).scalar_one() == 3
        bootstrap.verify_search_objects(connection)


def test_simultaneous_starts_serialize_schema_creation(pg_engine):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(bootstrap.init_db) for _ in range(2)]
        for future in futures:
            future.result(timeout=60)
    with pg_engine.connect() as connection:
        bootstrap.verify_search_objects(connection)


def test_bootstrap_failure_rolls_back_tables_and_revision(pg_engine, monkeypatch):
    def fail(_connection):
        raise RuntimeError("injected index failure")
    monkeypatch.setattr(bootstrap, "install_search_objects", fail)
    with pytest.raises(RuntimeError, match="injected index failure"):
        bootstrap.init_db()
    assert not (set(inspect(pg_engine).get_table_names()) & set(Base.metadata.tables))
    assert not inspect(pg_engine).has_table("alembic_version")


def test_upgrade_repairs_old_stamped_database_without_losing_books(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION vector"))
        Base.metadata.create_all(connection)
        connection.execute(text("DROP TABLE reading_prefs"))
        connection.execute(text("CREATE INDEX ix_chunks_embedding_hnsw ON chunks (order_index)"))
        command.stamp(bootstrap.migration_config(connection), "006")
    seed_book(pg_engine)
    bootstrap.init_db()
    with pg_engine.connect() as connection:
        bootstrap.verify_search_objects(connection)
        assert connection.execute(text("SELECT count(*) FROM chunks")).scalar_one() == 3
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "007"
    assert inspect(pg_engine).has_table("reading_prefs")


def test_unversioned_library_is_not_silently_stamped(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION vector"))
        Base.metadata.create_all(connection)
    seed_book(pg_engine)
    with pytest.raises(RuntimeError, match="no migration revision"):
        bootstrap.init_db()
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM books")).scalar_one() == 2
    assert not inspect(pg_engine).has_table("alembic_version")


def test_downgrade_preserves_data_and_search_objects(pg_engine):
    bootstrap.init_db()
    seed_book(pg_engine)
    with pg_engine.begin() as connection:
        command.downgrade(bootstrap.migration_config(connection), "006")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "006"
        assert connection.execute(text("SELECT count(*) FROM chunks")).scalar_one() == 3
        bootstrap.verify_search_objects(connection)
    bootstrap.init_db()
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "007"
        bootstrap.verify_search_objects(connection)


def test_missing_index_at_head_stops_startup(pg_engine):
    bootstrap.init_db()
    with pg_engine.begin() as connection:
        connection.execute(text("DROP INDEX idx_chunks_text_search"))
    with pytest.raises(RuntimeError, match="idx_chunks_text_search"):
        bootstrap.init_db()


def test_explicit_adoption_validates_and_preserves_unversioned_library(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION vector"))
        Base.metadata.create_all(connection)
    seed_book(pg_engine)
    bootstrap.init_db(adopt_unversioned=True)
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM books")).scalar_one() == 2
        bootstrap.verify_search_objects(connection)


def test_incompatible_legacy_schema_is_unchanged_after_rejected_adoption(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION vector"))
        Base.metadata.create_all(connection)
        connection.execute(text("ALTER TABLE books DROP COLUMN author"))
    with pytest.raises(RuntimeError, match="missing column books.author"):
        bootstrap.init_db(adopt_unversioned=True)
    assert not inspect(pg_engine).has_table("alembic_version")


def test_failed_upgrade_rolls_back_data_changes_and_revision(pg_engine, monkeypatch):
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION vector"))
        Base.metadata.create_all(connection)
        command.stamp(bootstrap.migration_config(connection), "006")
    seed_book(pg_engine)
    def fail(config, _revision):
        config.attributes['connection'].execute(text("UPDATE books SET title = 'partial migration'"))
        raise RuntimeError("injected migration failure")
    monkeypatch.setattr(command, "upgrade", fail)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        bootstrap.init_db()
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT title FROM books WHERE id = 'book'")).scalar_one() == "Fixture book"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "006"


@pytest.mark.asyncio
async def test_real_hybrid_search_stays_in_book_and_reading_slice(pg_engine, monkeypatch):
    bootstrap.init_db()
    seed_book(pg_engine)
    embeddings = MagicMock()
    embeddings.embed_single = AsyncMock(return_value=[1.0] + [0.0] * 3071)
    monkeypatch.setattr(search, "get_embeddings_client", lambda: embeddings)
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(search, "get_embedding_cache", lambda: cache)
    with Session(pg_engine) as db:
        vector = await search.vector_search(db, "book", "cartographer", section_ids=["read"])
        assert [r.chunk_id for r in vector] == ["read"]
        assert vector[0].score == pytest.approx(1.0)
        assert [r.chunk_id for r in search.fts_search(db, "book", "cartographer", section_ids=["read"])] == ["read"]
        hybrid = await search.hybrid_search(db, "book", "cartographer", section_ids=["read"], rerank=False)
        assert [r.chunk_id for r in hybrid] == ["read"]
        embeddings.embed_single.reset_mock()
        assert await search.vector_search(db, "book", "cartographer", section_ids=[]) == []
        assert search.fts_search(db, "book", "cartographer", section_ids=[]) == []
        embeddings.embed_single.assert_not_called()


def test_hnsw_expression_is_usable_by_postgres(pg_engine):
    bootstrap.init_db()
    seed_book(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = connection.execute(text("""
            EXPLAIN SELECT id FROM chunks
            ORDER BY embedding::halfvec(3072) <=> CAST(:query AS halfvec(3072)) LIMIT 5
        """), {"query": "[" + ",".join(["1"] + ["0"] * 3071) + "]"}).scalars().all()
        assert "ix_chunks_embedding_hnsw" in "\n".join(plan)


def test_fts_failure_does_not_erase_pending_work_or_log_queries(pg_engine, caplog):
    bootstrap.init_db()
    seed_book(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("ALTER TABLE chunks DROP COLUMN text_search CASCADE"))
    with Session(pg_engine) as db:
        db.get(Book, "book").title = "Saved reader change"
        db.flush()
        assert search.fts_search(db, "book", "sensitive-reader-query") == []
        db.commit()
    with Session(pg_engine) as db:
        assert db.get(Book, "book").title == "Saved reader change"
    assert "sensitive-reader-query" not in caplog.text
