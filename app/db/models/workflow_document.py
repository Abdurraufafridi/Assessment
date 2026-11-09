"""Workflow-to-document association model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import utc_now
from app.domain.enums import DocumentRole

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.workflow import Workflow


class WorkflowDocument(Base):
    """Associates a document with a workflow and records its role."""

    __tablename__ = "workflow_documents"

    workflow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[DocumentRole] = mapped_column(
        SAEnum(
            DocumentRole,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=DocumentRole.REFERENCE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    workflow: Mapped[Workflow] = relationship(back_populates="document_links")
    document: Mapped[Document] = relationship(back_populates="workflow_links")

    __table_args__ = (Index("ix_workflow_documents_document_id", "document_id"),)
