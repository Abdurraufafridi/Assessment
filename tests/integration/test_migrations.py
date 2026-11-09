"""Alembic migration and metadata-parity tests."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db import models  # noqa: F401  (registers metadata)
from app.db.base import Base
from app.db.database import Database

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
    "agent_executions",
    "alembic_version",
    "documents",
    "tasks",
    "users",
    "workflow_documents",
    "workflows",
}


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = database_url
    return config


def test_migrations_upgrade_downgrade_and_match_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    database = Database(database_url)
    database.dispose()
    config = _alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES

        task_foreign_keys = inspector.get_foreign_keys("tasks")
        assert {
            (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
            for foreign_key in task_foreign_keys
        } >= {
            ("workflow_id", "workflows"),
            ("input_document_id", "documents"),
            ("output_document_id", "documents"),
        }

        document_indexes = {index["name"] for index in inspector.get_indexes("documents")}
        assert "ix_documents_content_hash" in document_indexes
        assert "ix_documents_owner_kind" in document_indexes

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()
