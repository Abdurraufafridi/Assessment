"""Unit tests for the document repository."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.database import Database
from app.db.models.document import IngestionStatus
from app.repositories.documents import DocumentRepository

pytestmark = pytest.mark.unit


def _create(
    repository: DocumentRepository,
    document_id: str = "doc-1",
    content_hash: str = "hash-1",
) -> None:
    repository.create(
        document_id=document_id,
        source_name="proposal_logistics.txt",
        source_type="txt",
        content_hash=content_hash,
        byte_size=120,
        embedding_provider="sentence_transformers",
        embedding_model="test-model",
        document_metadata={"industry": "logistics"},
    )


def test_create_and_transition_document_status(database: Database) -> None:
    with database.session() as session:
        repository = DocumentRepository(session)
        document = repository.create(
            document_id="doc-1",
            source_name="proposal_logistics.txt",
            source_type="txt",
            content_hash="hash-1",
            byte_size=120,
            embedding_provider="sentence_transformers",
            embedding_model="test-model",
            document_metadata={"industry": "logistics"},
        )
        assert document.status == IngestionStatus.PENDING

        repository.mark_processing(document)
        repository.mark_completed(document, 4, document_metadata={"industry": "logistics"})
        session.commit()

    with database.session() as session:
        stored = DocumentRepository(session).get("doc-1")

    assert stored is not None
    assert stored.status == IngestionStatus.COMPLETED
    assert stored.chunk_count == 4
    assert stored.indexed_at is not None


def test_mark_failed_records_truncated_error(database: Database) -> None:
    with database.session() as session:
        repository = DocumentRepository(session)
        document = repository.create(
            document_id="doc-1",
            source_name="proposal_logistics.txt",
            source_type="txt",
            content_hash="hash-1",
            byte_size=120,
            embedding_provider="sentence_transformers",
            embedding_model="test-model",
            document_metadata={},
        )
        repository.mark_failed(document, "x" * 3000)
        session.commit()
        assert document.error_message is not None
        assert len(document.error_message) == 2000


def test_content_hash_is_unique(database: Database) -> None:
    with database.session() as session:
        repository = DocumentRepository(session)
        _create(repository, "doc-1")
        session.commit()

    with pytest.raises(IntegrityError), database.session() as session:
        repository = DocumentRepository(session)
        _create(repository, "doc-2")
        session.commit()
