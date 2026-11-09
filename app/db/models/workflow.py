"""Workflow state model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import WorkflowStage, WorkflowStatus

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.task import Task
    from app.db.models.user import User
    from app.db.models.workflow_document import WorkflowDocument


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A proposal workflow and its serialized application state."""

    __tablename__ = "workflows"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[WorkflowStage] = mapped_column(
        SAEnum(
            WorkflowStage,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=WorkflowStage.INTAKE,
        index=True,
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        SAEnum(
            WorkflowStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=WorkflowStatus.PENDING,
        index=True,
    )
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    input_document_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    output_document_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="workflows")
    document_links: Mapped[list[WorkflowDocument]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Task.sequence",
    )
    input_document: Mapped[Document | None] = relationship(
        foreign_keys=[input_document_id],
    )
    output_document: Mapped[Document | None] = relationship(
        foreign_keys=[output_document_id],
    )

    __table_args__ = (
        CheckConstraint("state_version >= 1", name="state_version_positive"),
        Index("ix_workflows_user_status", "user_id", "status"),
        Index("ix_workflows_status_updated_at", "status", "updated_at"),
    )
