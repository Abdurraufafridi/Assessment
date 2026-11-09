"""End-to-end document ingestion pipeline."""

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.database import Database
from app.db.models.document import IngestionDocument, IngestionStatus
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import create_embedding_provider
from app.ingestion.chunking import ChunkingConfig, TextChunker
from app.ingestion.cleaning import clean_text
from app.ingestion.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    IngestionError,
    UnsupportedDocumentTypeError,
)
from app.ingestion.loaders import DocumentLoaderRegistry
from app.ingestion.metadata import Metadata, infer_metadata, normalise_metadata
from app.repositories.documents import DocumentRepository
from app.vectorstore.base import VectorStore
from app.vectorstore.factory import create_vector_store

logger = get_logger(__name__)


class IngestionOutcome(StrEnum):
    """Outcome of an ingestion request."""

    COMPLETED = "completed"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Summary returned after an ingestion attempt."""

    document_id: str
    source_name: str
    content_hash: str
    status: IngestionOutcome
    chunk_count: int
    embedding_provider: str
    embedding_model: str


class IngestionPipeline:
    """Load, clean, chunk, embed, and index a document exactly once.

    Duplicate detection is based on the SHA-256 hash of the raw file content.
    Completed documents with the same hash are reported as duplicates unless
    ``force=True`` is supplied.
    """

    def __init__(
        self,
        *,
        database: Database,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        chunker: TextChunker,
        loader_registry: DocumentLoaderRegistry | None = None,
        max_file_size_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self._database = database
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._chunker = chunker
        self._loaders = loader_registry or DocumentLoaderRegistry()
        self._max_file_size_bytes = max_file_size_bytes

    @classmethod
    def from_settings(cls, database: Database, settings: Settings) -> "IngestionPipeline":
        """Build a pipeline from environment settings."""

        return cls(
            database=database,
            embeddings=create_embedding_provider(settings),
            vector_store=create_vector_store(settings),
            chunker=TextChunker(
                ChunkingConfig(
                    chunk_size=settings.ingestion_chunk_size,
                    chunk_overlap=settings.ingestion_chunk_overlap,
                    min_chunk_size=settings.ingestion_min_chunk_size,
                    boundary_search_chars=settings.ingestion_boundary_search_chars,
                )
            ),
            max_file_size_bytes=settings.ingestion_max_file_size_mb * 1024 * 1024,
        )

    def ingest_file(
        self,
        path: str | Path,
        *,
        metadata: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest a single document into the vector store."""

        source_path = Path(path)
        if not source_path.is_file():
            raise IngestionError(f"Document does not exist or is not a file: {source_path}")

        if source_path.suffix.lower() not in self._loaders.supported_extensions:
            supported = ", ".join(sorted(self._loaders.supported_extensions))
            raise UnsupportedDocumentTypeError(
                f"Unsupported document type '{source_path.suffix}' for "
                f"{source_path.name}; supported: {supported}"
            )

        try:
            size = source_path.stat().st_size
        except OSError as exc:
            raise IngestionError(f"Unable to inspect {source_path.name}: {exc}") from exc
        if size > self._max_file_size_bytes:
            raise DocumentTooLargeError(
                f"{source_path.name} is {size} bytes, exceeding the "
                f"{self._max_file_size_bytes}-byte ingestion limit"
            )
        if size == 0:
            raise EmptyDocumentError(f"{source_path.name} is empty")

        try:
            raw_bytes = source_path.read_bytes()
        except OSError as exc:
            raise IngestionError(f"Unable to read {source_path.name}: {exc}") from exc

        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        merged_metadata = normalise_metadata({**infer_metadata(source_path), **(metadata or {})})

        document, is_duplicate, existing_chunk_count = self._prepare_document(
            source_path=source_path,
            content_hash=content_hash,
            byte_size=size,
            metadata=merged_metadata,
            force=force,
        )
        if is_duplicate:
            logger.info(
                "ingestion_duplicate_skipped",
                extra={
                    "document_id": document.id,
                    "source_name": source_path.name,
                    "content_hash": content_hash,
                },
            )
            return IngestionResult(
                document_id=document.id,
                source_name=document.source_name,
                content_hash=content_hash,
                status=IngestionOutcome.DUPLICATE,
                chunk_count=existing_chunk_count,
                embedding_provider=document.embedding_provider or self._embeddings.provider_name,
                embedding_model=document.embedding_model or self._embeddings.model_name,
            )

        started_at = datetime.now(UTC)
        logger.info(
            "ingestion_started",
            extra={
                "document_id": document.id,
                "source_name": source_path.name,
                "content_hash": content_hash,
                "byte_size": size,
            },
        )

        try:
            extracted = self._loaders.load(source_path)
            cleaned_text = clean_text(extracted.text)
            if not cleaned_text:
                raise EmptyDocumentError(
                    f"No usable text could be extracted from {source_path.name}"
                )

            chunks = self._chunker.split(cleaned_text)
            if not chunks:
                raise EmptyDocumentError(f"No chunks were produced for {source_path.name}")

            chunk_metadatas = [
                normalise_metadata(
                    {
                        **merged_metadata,
                        "document_id": document.id,
                        "source_name": source_path.name,
                        "source_type": extracted.file_type,
                        "content_hash": content_hash,
                        "chunk_index": chunk.index,
                        "chunk_count": len(chunks),
                    }
                )
                for chunk in chunks
            ]
            chunk_texts = [chunk.text for chunk in chunks]

            embeddings = self._embeddings.embed_documents(chunk_texts)
            self._validate_embeddings(embeddings, expected_count=len(chunks))

            self._vector_store.delete_document(document.id)
            self._vector_store.upsert_chunks(
                ids=[f"{document.id}:{chunk.index:04d}" for chunk in chunks],
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=chunk_metadatas,
            )

            self._update_status(
                document.id,
                completed=True,
                chunk_count=len(chunks),
                document_metadata=merged_metadata,
            )

            elapsed_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
            logger.info(
                "ingestion_completed",
                extra={
                    "document_id": document.id,
                    "source_name": source_path.name,
                    "chunk_count": len(chunks),
                    "embedding_dimension": self._embeddings.dimension,
                    "elapsed_ms": elapsed_ms,
                },
            )
            return IngestionResult(
                document_id=document.id,
                source_name=document.source_name,
                content_hash=content_hash,
                status=IngestionOutcome.COMPLETED,
                chunk_count=len(chunks),
                embedding_provider=document.embedding_provider or self._embeddings.provider_name,
                embedding_model=document.embedding_model or self._embeddings.model_name,
            )
        except Exception as exc:
            self._mark_failed(document.id, exc)
            logger.exception(
                "ingestion_failed",
                extra={
                    "document_id": document.id,
                    "source_name": source_path.name,
                    "error_type": type(exc).__name__,
                },
            )
            if isinstance(exc, IngestionError):
                raise
            raise IngestionError(
                f"Unexpected failure while ingesting {source_path.name}: {exc}"
            ) from exc

    def _prepare_document(
        self,
        *,
        source_path: Path,
        content_hash: str,
        byte_size: int,
        metadata: Metadata,
        force: bool,
    ) -> tuple[IngestionDocument, bool, int]:
        with self._database.session() as session:
            repository = DocumentRepository(session)
            existing = repository.get_by_content_hash(content_hash)

            if existing is not None and existing.status == IngestionStatus.COMPLETED and not force:
                return existing, True, existing.chunk_count

            if existing is not None:
                repository.prepare_for_processing(
                    existing,
                    source_name=source_path.name,
                    source_type=source_path.suffix.lstrip(".").lower(),
                    byte_size=byte_size,
                    embedding_provider=self._embeddings.provider_name,
                    embedding_model=self._embeddings.model_name,
                    document_metadata=dict(metadata),
                )
                document = existing
            else:
                document = repository.create(
                    document_id=str(uuid.uuid4()),
                    source_name=source_path.name,
                    source_type=source_path.suffix.lstrip(".").lower(),
                    content_hash=content_hash,
                    byte_size=byte_size,
                    embedding_provider=self._embeddings.provider_name,
                    embedding_model=self._embeddings.model_name,
                    document_metadata=dict(metadata),
                )
                repository.mark_processing(document)

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = repository.get_by_content_hash(content_hash)
                if existing is None:
                    raise
                return existing, True, existing.chunk_count

            session.refresh(document)
            return document, False, 0

    def _validate_embeddings(self, embeddings: list[list[float]], *, expected_count: int) -> None:
        if len(embeddings) != expected_count:
            raise IngestionError(
                f"Embedding provider returned {len(embeddings)} vectors for {expected_count} chunks"
            )
        expected_dimension = self._embeddings.dimension
        for index, vector in enumerate(embeddings):
            if len(vector) != expected_dimension:
                raise IngestionError(
                    f"Embedding dimension mismatch at chunk {index}: expected "
                    f"{expected_dimension}, received {len(vector)}"
                )

    def _mark_failed(self, document_id: str, error: Exception) -> None:
        self._update_status(
            document_id,
            completed=False,
            error_message=f"{type(error).__name__}: {error}",
        )

    def _update_status(
        self,
        document_id: str,
        *,
        completed: bool,
        chunk_count: int = 0,
        document_metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        try:
            with self._database.session() as session:
                repository = DocumentRepository(session)
                document = repository.get(document_id)
                if document is None:
                    logger.error("ingestion_document_missing", extra={"document_id": document_id})
                    return
                if completed:
                    repository.mark_completed(
                        document,
                        chunk_count,
                        document_metadata=document_metadata,
                    )
                elif error_message is not None:
                    repository.mark_failed(document, error_message)
                session.commit()
        except SQLAlchemyError:
            logger.exception("ingestion_status_update_failed", extra={"document_id": document_id})
