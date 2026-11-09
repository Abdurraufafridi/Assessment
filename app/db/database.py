"""Database engine and session factory abstraction."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.logging import get_logger

logger = get_logger(__name__)


class Database:
    """Owns the SQLAlchemy engine and session factory.

    Only SQLite-specific connection options are applied for SQLite URLs, so the
    same class works with PostgreSQL by changing ``DATABASE_URL``.
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self._url = make_url(database_url)
        self._backend = self._url.get_backend_name()
        self._ensure_sqlite_directory()

        connect_args: dict[str, object] = {}
        engine_options: dict[str, object] = {}

        if self._backend == "sqlite":
            connect_args["check_same_thread"] = False
            if self._url.database in {None, "", ":memory:"}:
                engine_options["poolclass"] = StaticPool

        self._engine: Engine = create_engine(
            self._url,
            echo=echo,
            pool_pre_ping=True,
            connect_args=connect_args,
            **engine_options,
        )
        if self._backend == "sqlite":
            event.listen(self._engine, "connect", self._configure_sqlite_connection)
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    @property
    def engine(self) -> Engine:
        """Return the underlying SQLAlchemy engine."""

        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Return the configured session factory."""

        return self._session_factory

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a session that is always closed after use."""

        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def create_all(self) -> None:
        """Create missing tables for local development and tests.

        Production deployments use Alembic migrations; the test suite includes
        a metadata-parity check between the migrations and ORM models.
        """

        from app.db import models  # noqa: F401  (registers model metadata)
        from app.db.base import Base

        Base.metadata.create_all(self._engine)

    def check_connection(self) -> bool:
        """Return ``True`` when a trivial query succeeds against the database."""

        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("database_connection_check_failed")
            return False
        return True

    def dispose(self) -> None:
        """Dispose pooled connections during application shutdown."""

        self._engine.dispose()

    @staticmethod
    def _configure_sqlite_connection(dbapi_connection: Any, connection_record: Any) -> None:
        """Enable foreign-key enforcement for every SQLite connection."""

        del connection_record
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    def _ensure_sqlite_directory(self) -> None:
        if self._backend != "sqlite":
            return

        database_name = self._url.database
        if not database_name or database_name == ":memory:":
            return

        database_path = Path(database_name)
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
