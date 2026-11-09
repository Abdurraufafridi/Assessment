"""Reusable ORM mixins and timestamp helpers."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    """Return the current aware UTC timestamp."""

    return datetime.now(UTC)


def generate_uuid() -> str:
    """Return a string UUID suitable for portable SQLite/PostgreSQL keys."""

    return str(uuid4())


class UUIDPrimaryKeyMixin:
    """String UUID primary key shared by domain entities."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)


class TimestampMixin:
    """Creation and update timestamps shared by domain entities."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
