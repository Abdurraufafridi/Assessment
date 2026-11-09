"""Document registry and ingestion tracking model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin
from app.domain.enums import DocumentKind, DocumentStatus

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.workflow_document import WorkflowDocument


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A document stored by the application.

    The same record is used for ingested source material and generated
    artifacts. Ingestion-specific fields remain on the document so the Phase 1
    pipeline continues to work unchanged.
    """

    __tablename__ = "documents"

    owner_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[DocumentKind] = mapped_column(
        SAEnum(
            DocumentKind,
            native_enum=False,
            length=30,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=DocumentKind.REFERENCE,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=DocumentStatus.PENDING,
        index=True,
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User | None] = relationship(back_populates="documents")
    workflow_links: Mapped[list[WorkflowDocument]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        CheckConstraint("chunk_count >= 0", name="chunk_count_non_negative"),
        CheckConstraint("length(trim(source_name)) > 0", name="source_name_not_blank"),
        Index("ix_documents_owner_kind", "owner_id", "kind"),
        Index("ix_documents_kind_status", "kind", "status"),
    )


# Phase 1 compatibility aliases. New code should use Document/DocumentStatus.
IngestionDocument = Document
IngestionStatus = DocumentStatus

__all__ = ["Document", "DocumentKind", "DocumentStatus", "IngestionDocument", "IngestionStatus"]
