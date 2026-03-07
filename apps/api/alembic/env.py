"""Alembic environment configuration.

Imports database URL from app.settings and Base metadata from app.db.models
so that autogenerate can detect schema changes.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, text
from alembic import context

# ---------------------------------------------------------------------------
# Ensure the project root (apps/api) is on sys.path so that "app" is importable.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import settings  # noqa: E402
from app.db.models import Base  # noqa: E402

# Alembic Config object (provides access to .ini values).
config = context.config

# Override sqlalchemy.url with the real value from app settings.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from the alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData object used by autogenerate to detect changes.
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# pgvector Vector type -- teach Alembic to compare / render it correctly.
# Without this, autogenerate will try to re-create vector columns every run.
# ---------------------------------------------------------------------------
from pgvector.sqlalchemy import Vector  # noqa: E402

def _render_vector_type(type_, autogen_context):
    """Render Vector(dim) in migration scripts."""
    if isinstance(type_, Vector):
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector({type_.dim})"
    return False


# ---------------------------------------------------------------------------
# Offline (SQL-only) migrations
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to a live database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=_render_vector_type,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online (connected) migrations
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Ensure pgvector extension exists before running any migrations.
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=_render_vector_type,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
