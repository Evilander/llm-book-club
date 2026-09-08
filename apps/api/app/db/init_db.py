"""Initialize the database with all tables and extensions.

Prefers running Alembic migrations (so that indexes, generated columns,
and future schema changes are applied consistently). Falls back to
SQLAlchemy ``create_all`` if Alembic is not installed or if the migration
runner fails for any reason (e.g. missing alembic.ini in a test environment).
"""
import logging
from pathlib import Path

from sqlalchemy import text
from .engine import engine
from .models import Base

logger = logging.getLogger(__name__)


def _run_alembic_upgrade() -> bool:
    """Attempt to run ``alembic upgrade head`` programmatically.

    Returns True on success, False if Alembic is unavailable or fails.
    """
    try:
        from alembic.config import Config
        from alembic import command
    except ImportError:
        logger.warning("alembic package not installed -- skipping migrations")
        return False

    # Locate alembic.ini relative to the project root (apps/api/).
    api_root = Path(__file__).resolve().parents[2]  # apps/api/
    ini_path = api_root / "alembic.ini"

    if not ini_path.exists():
        logger.warning("alembic.ini not found at %s -- skipping migrations", ini_path)
        return False

    try:
        alembic_cfg = Config(str(ini_path))
        # Override script_location to an absolute path so it works
        # regardless of the process working directory.
        alembic_cfg.set_main_option(
            "script_location", str(api_root / "alembic")
        )
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
        return True
    except Exception:
        logger.exception("Alembic migration failed -- falling back to create_all")
        return False


def init_db():
    """Create all tables and enable required extensions.

    1. Enable the pgvector extension.
    2. If the DB is empty (no ``books`` table yet), bootstrap from the ORM
       so that downstream migrations don't try to touch tables that haven't
       been created yet. Stamp Alembic at head once tables exist.
    3. Otherwise run ``alembic upgrade head`` normally so future schema
       changes apply on top of an existing database.
    4. If Alembic isn't available at all, fall back to ``create_all``.
    """
    with engine.connect() as conn:
        # Enable pgvector extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

        # Detect whether this looks like a fresh database.
        result = conn.execute(text(
            "SELECT to_regclass('public.books') IS NOT NULL"
        )).scalar()
        is_fresh = not bool(result)

    if is_fresh:
        # Fresh DB: create tables from the ORM, then stamp Alembic at head
        # so subsequent migrations have a known starting point.
        logger.info("Fresh database detected -- bootstrapping via ORM")
        Base.metadata.create_all(bind=engine)
        try:
            from alembic.config import Config
            from alembic import command
            api_root = Path(__file__).resolve().parents[2]
            cfg = Config(str(api_root / "alembic.ini"))
            cfg.set_main_option("script_location", str(api_root / "alembic"))
            command.stamp(cfg, "head")
            logger.info("Alembic stamped at head")
        except Exception:
            logger.exception("Could not stamp Alembic -- continuing without")
        return

    # Existing DB: run migrations as usual.
    migrated = _run_alembic_upgrade()
    if not migrated:
        logger.info("Falling back to Base.metadata.create_all()")
        Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
