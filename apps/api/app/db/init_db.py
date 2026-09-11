"""Initialize or migrate Postgres atomically; a broken schema must stop startup."""
import logging
import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from .engine import engine
from .models import Base
from .search_schema import install_search_objects, verify_search_objects

logger = logging.getLogger(__name__)
SCHEMA_LOCK = 732_041_907


def migration_config(connection=None) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    ini_path = api_root / "alembic.ini"
    if not ini_path.is_file() or not (api_root / "alembic/versions").is_dir():
        raise RuntimeError("Database migrations are missing from this installation.")
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(api_root / "alembic"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def validate_unversioned_library(connection) -> None:
    """Accept only the known ORM layout; never guess a partial legacy version."""
    schema = inspect(connection)
    tables = set(schema.get_table_names())
    problems = []
    for name, table in Base.metadata.tables.items():
        if name not in tables:
            if name != "reading_prefs":  # Migration 007 creates this known omission.
                problems.append(f"missing table {name}")
            continue
        columns = {column['name']: column for column in schema.get_columns(name)}
        for expected in table.columns:
            actual = columns.get(expected.name)
            if actual is None:
                problems.append(f"missing column {name}.{expected.name}")
                continue
            expected_type = expected.type.compile(dialect=connection.dialect).upper()
            actual_type = actual['type'].compile(dialect=connection.dialect).upper()
            # PostgreSQL reflects SQLAlchemy's unqualified FLOAT as DOUBLE PRECISION.
            expected_type = expected_type.replace("DOUBLE PRECISION", "FLOAT")
            actual_type = actual_type.replace("DOUBLE PRECISION", "FLOAT")
            if expected_type != actual_type or expected.nullable != actual['nullable']:
                problems.append(f"incompatible column {name}.{expected.name}")
            if getattr(expected.type, 'enums', None) != getattr(actual['type'], 'enums', None):
                problems.append(f"incompatible enum {name}.{expected.name}")
        primary_key = set(schema.get_pk_constraint(name)['constrained_columns'])
        if primary_key != {column.name for column in table.primary_key}:
            problems.append(f"incompatible primary key {name}")
    if problems:
        raise RuntimeError("Legacy schema does not match this release; no changes were applied: " + "; ".join(problems[:12]))


def init_db(*, adopt_unversioned: bool = False):
    if engine.dialect.name != "postgresql":
        raise RuntimeError("ReadAgain requires PostgreSQL with pgvector for its library.")

    # API processes and the migration service may start together. One transaction
    # owns schema creation, derived indexes, and the revision stamp as a unit.
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '60s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCHEMA_LOCK})
        config = migration_config(connection)
        heads = ScriptDirectory.from_config(config).get_heads()
        if len(heads) != 1:
            raise RuntimeError("Database migrations must have exactly one head.")
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        version = connection.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar_one()
        if tuple(int(part) for part in version.split('.')[:2]) < (0, 8):
            raise RuntimeError("ReadAgain requires pgvector 0.8 or newer. Upgrade the extension before restarting.")

        revisions = MigrationContext.configure(connection).get_current_heads()
        tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
        if not revisions:
            if tables & set(Base.metadata.tables):
                # Old create_all installs sometimes have data but no revision.
                # Guessing their version could mark missing columns as migrated.
                if not adopt_unversioned:
                    raise RuntimeError(
                        "This library has tables but no migration revision. Back up the database "
                        "and follow the legacy-library recovery instructions before restarting."
                    )
                validate_unversioned_library(connection)
                command.stamp(config, "006")
                command.upgrade(config, "head")
            else:
                Base.metadata.create_all(bind=connection)
                install_search_objects(connection)
                command.stamp(config, heads[0])
        else:
            command.upgrade(config, "head")

        verify_search_objects(connection)
        if MigrationContext.configure(connection).get_current_heads() != tuple(heads):
            raise RuntimeError("Database migration did not reach the expected revision.")
    logger.info("Database schema and retrieval indexes are ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or migrate the library database.")
    parser.add_argument("--adopt-unversioned", action="store_true", help="After a backup, validate and adopt an unversioned library with this release's known schema.")
    init_db(adopt_unversioned=parser.parse_args().adopt_unversioned)
    print("Database initialized successfully.")
