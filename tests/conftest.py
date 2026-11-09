"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.database import Database
from app.main import create_app


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    """Temporary SQLite database with all current tables created."""

    instance = Database(f"sqlite:///{tmp_path / 'unit.db'}")
    instance.create_all()
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Isolated settings pointing at a temporary SQLite database."""

    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        app_name="Proposal Research Agent Test",
        app_version="0.0.0-test",
        log_level="WARNING",
        log_format="json",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    """FastAPI test client with lifespan and database wiring active."""

    with TestClient(create_app(test_settings)) as test_client:
        yield test_client
