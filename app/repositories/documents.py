"""Repository for document records."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document, DocumentKind, DocumentStatus


class DocumentRepository:
    """Data-access operations for :class:`Document`.

    The repository never commits; callers own transaction boundaries.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, document_id: str) -> Document | None:
        return self._session.get(Document, document_id)

    def get_by_content_hash(self, content_hash: str) -> Document | None:
        statement = select(Document).where(Document.content_hash == content_hash)
        return self._session.execute(statement).scalar_one_or_none()

    def list_by_owner(self, owner_id: str, *, limit: int = 100, offset: int = 0) -> list[Document]:
        statement = (
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(statement).scalars())

    def create(
        self,
        *,
        document_id: str,
        source_name: str,
        source_type: str,
        content_hash: str,
        byte_size: int,
        embedding_provider: str,
        embedding_model: str,
        document_metadata: dict[str, Any],
        owner_id: str | None = None,
        kind: DocumentKind = DocumentKind.REFERENCE,
        storage_path: str | None = None,
    ) -> Document:
        document = Document(
            id=document_id,
            owner_id=owner_id,
            kind=kind,
            source_name=source_name,
            source_type=source_type,
            storage_path=storage_path,
            content_hash=content_hash,
            byte_size=byte_size,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            document_metadata=document_metadata,
            status=DocumentStatus.PENDING,
        )
        self._session.add(document)
        self._session.flush()
        return document

    def prepare_for_processing(
        self,
        document: Document,
        *,
        source_name: str,
        source_type: str,
        byte_size: int,
        embedding_provider: str,
        embedding_model: str,
        document_metadata: dict[str, Any],
    ) -> None:
        document.source_name = source_name
        document.source_type = source_type
        document.byte_size = byte_size
        document.embedding_provider = embedding_provider
        document.embedding_model = embedding_model
        document.document_metadata = document_metadata
        document.status = DocumentStatus.PROCESSING
        document.error_message = None

    def mark_processing(self, document: Document) -> None:
        document.status = DocumentStatus.PROCESSING
        document.error_message = None

    def mark_completed(
        self,
        document: Document,
        chunk_count: int,
        *,
        document_metadata: dict[str, Any] | None = None,
    ) -> None:
        document.status = DocumentStatus.COMPLETED
        document.chunk_count = chunk_count
        document.error_message = None
        document.indexed_at = datetime.now(UTC)
        if document_metadata is not None:
            document.document_metadata = document_metadata

    def mark_failed(self, document: Document, error_message: str) -> None:
        document.status = DocumentStatus.FAILED
        document.error_message = error_message[:2000]

    def delete(self, document: Document) -> None:
        self._session.delete(document)
