"""Real Postgres fixtures. Run separately from the SQLite unit-test process.

TEST_DATABASE_URL must point to an isolated server with CREATE DATABASE rights.
Each test creates and removes only a uniquely named readagain_test_* database.
"""
import os
from pathlib import Path
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_URL:
    raise pytest.UsageError("Set TEST_DATABASE_URL to an isolated Postgres server; see docs/development.md.")
if make_url(TEST_URL).get_backend_name() != "postgresql":
    raise pytest.UsageError("The integration suite requires real PostgreSQL with pgvector.")

os.environ["DATABASE_URL"] = TEST_URL
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:56379/0")
os.environ["APP_ENV"] = "test"
os.environ["EMBEDDINGS_PROVIDER"] = "openai"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import init_db as bootstrap  # noqa: E402


@pytest.fixture
def pg_engine(monkeypatch):
    name = "readagain_test_" + uuid.uuid4().hex
    admin = create_engine(TEST_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(make_url(TEST_URL).set(database=name), pool_pre_ping=True)
    monkeypatch.setattr(bootstrap, "engine", engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
