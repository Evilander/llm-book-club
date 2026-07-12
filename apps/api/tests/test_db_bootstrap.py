"""Database bootstrap decisions for fresh and established installations."""

from unittest.mock import MagicMock, patch

import app.db.init_db as init_module


def fake_engine(dialect: str):
    engine = MagicMock()
    engine.dialect.name = dialect
    connection = engine.connect.return_value.__enter__.return_value
    return engine, connection


def test_fresh_postgres_bootstraps_metadata_objects_and_revision():
    engine, connection = fake_engine("postgresql")
    inspector = MagicMock()
    inspector.has_table.return_value = False

    with patch.object(init_module, "engine", engine), patch.object(
        init_module, "inspect", return_value=inspector
    ), patch.object(init_module.Base.metadata, "create_all") as create_all, patch.object(
        init_module, "_install_postgres_search_objects"
    ) as install_objects, patch.object(
        init_module, "_stamp_alembic_head", return_value=True
    ) as stamp, patch.object(init_module, "_run_alembic_upgrade") as upgrade:
        init_module.init_db()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in str(
        connection.execute.call_args.args[0]
    )
    create_all.assert_called_once_with(bind=engine)
    install_objects.assert_called_once_with()
    stamp.assert_called_once_with()
    upgrade.assert_not_called()


def test_established_database_runs_forward_migrations():
    engine, _ = fake_engine("postgresql")
    inspector = MagicMock()
    inspector.has_table.return_value = True

    with patch.object(init_module, "engine", engine), patch.object(
        init_module, "inspect", return_value=inspector
    ), patch.object(init_module.Base.metadata, "create_all") as create_all, patch.object(
        init_module, "_run_alembic_upgrade", return_value=True
    ) as upgrade:
        init_module.init_db()

    upgrade.assert_called_once_with()
    create_all.assert_not_called()


def test_fresh_sqlite_uses_metadata_without_postgres_objects():
    engine, _ = fake_engine("sqlite")
    inspector = MagicMock()
    inspector.has_table.return_value = False

    with patch.object(init_module, "engine", engine), patch.object(
        init_module, "inspect", return_value=inspector
    ), patch.object(init_module.Base.metadata, "create_all") as create_all, patch.object(
        init_module, "_install_postgres_search_objects"
    ) as install_objects, patch.object(init_module, "_stamp_alembic_head") as stamp:
        init_module.init_db()

    create_all.assert_called_once_with(bind=engine)
    install_objects.assert_not_called()
    stamp.assert_not_called()
