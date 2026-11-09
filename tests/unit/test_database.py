"""Unit tests for database connectivity."""

from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.database import Database

pytestmark = pytest.mark.unit


def test_database_creates_parent_directory_and_connects(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "app.db"
    database = Database(f"sqlite:///{database_path}")

    try:
        assert database.check_connection() is True
        assert database_path.exists()
    finally:
        database.dispose()


def test_in_memory_database_connects() -> None:
    database = Database("sqlite:///:memory:")

    try:
        assert database.check_connection() is True
        with database.session() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        database.dispose()


def test_disposed_database_still_reports_connection_after_reconnect(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'app.db'}")

    try:
        assert database.check_connection() is True
        database.dispose()
        assert database.check_connection() is True
    finally:
        database.dispose()
