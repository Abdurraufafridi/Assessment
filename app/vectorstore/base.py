"""Vector store interface and result types."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.ingestion.metadata import Metadata, MetadataValue


class VectorStoreError(Exception):
    """Base exception for vector-store failures."""


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """A chunk returned from a similarity search."""

    id: str
    text: str
    metadata: Metadata = field(default_factory=dict)
    distance: float = 0.0
    score: float = 0.0


class VectorStore(Protocol):
    """Provider-neutral interface for vector persistence and retrieval."""

    def upsert_chunks(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, MetadataValue]],
    ) -> None:
        """Insert or replace chunk records."""

    def query(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        """Return the most similar chunks, optionally filtered by metadata."""

    def get_document_chunks(self, document_id: str) -> list[VectorSearchResult]:
        """Return every stored chunk for a document."""

    def delete_document(self, document_id: str) -> None:
        """Delete all chunks belonging to a document."""

    def count(self) -> int:
        """Return the number of stored chunks."""
