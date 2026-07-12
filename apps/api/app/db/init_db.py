"""Initialize fresh databases and advance established Alembic schemas."""
import logging
from pathlib import Path

from sqlalchemy import inspect, text
from .engine import engine
from .models import Base

logger = logging.getLogger(__name__)


def _alembic_config():
    try:
        from alembic.config import Config
    except ImportError:
        return None

    api_root = Path(__file__).resolve().parents[2]
    ini_path = api_root / "alembic.ini"
    if not ini_path.exists():
        return None
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(api_root / "alembic"))
    return config


def _run_alembic_upgrade() -> bool:
    """Attempt to run ``alembic upgrade head`` programmatically.

    Returns True on success, False if Alembic is unavailable or fails.
    """
    try:
        from alembic import command
    except ImportError:
        logger.warning("alembic package not installed -- skipping migrations")
        return False
    alembic_cfg = _alembic_config()
    if alembic_cfg is None:
        logger.warning("alembic.ini or Alembic is unavailable -- skipping migrations")
        return False

    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
        return True
    except Exception:
        logger.exception("Alembic migration failed -- falling back to create_all")
        return False


def _stamp_alembic_head() -> bool:
    try:
        from alembic import command
    except ImportError:
        return False
    alembic_cfg = _alembic_config()
    if alembic_cfg is None:
        return False
    try:
        command.stamp(alembic_cfg, "head")
        return True
    except Exception:
        logger.exception("Could not stamp the fresh database at Alembic head")
        return False


def _install_postgres_search_objects() -> None:
    """Install schema objects that SQLAlchemy metadata cannot express."""
    statements = [
        "ALTER EXTENSION vector UPDATE",
        """
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS text_search tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_text_search
        ON chunks USING gin(text_search)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """,
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_db():
    """Create all tables and enable required extensions.

    Fresh Postgres databases cannot start at migration 001 because that
    historical revision adds indexes/columns to a pre-existing ORM schema.
    Bootstrap the current metadata, install Postgres-only derived objects,
    and stamp head. Databases with an Alembic version run normal upgrades.
    """
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    else:
        logger.info(
            "Skipping pgvector extension setup for %s (smoke-test mode)",
            engine.dialect.name,
        )

    has_revision = inspect(engine).has_table("alembic_version")
    if not has_revision:
        logger.info("Bootstrapping a fresh %s database", engine.dialect.name)
        Base.metadata.create_all(bind=engine)
        if engine.dialect.name == "postgresql":
            _install_postgres_search_objects()
            if not _stamp_alembic_head():
                raise RuntimeError("Fresh Postgres schema could not be stamped")
        return

    migrated = _run_alembic_upgrade()

    if not migrated:
        # Fallback: ensure at least the base tables exist.
        logger.info("Falling back to Base.metadata.create_all()")
        Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
