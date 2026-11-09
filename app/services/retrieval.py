"""RAG retrieval service for research agents."""

from collections.abc import Mapping
from typing import Protocol

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import create_embedding_provider
from app.ingestion.metadata import MetadataValue
from app.vectorstore.base import VectorSearchResult, VectorStore
from app.vectorstore.factory import create_vector_store


class RetrievalError(Exception):
    """Raised when a retrieval request is invalid."""


class Retriever(Protocol):
    """Provider-neutral interface used by the research agent."""

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        """Return the most relevant indexed chunks for a query."""


class RagRetriever:
    """Embed a query and search the configured persistent vector store."""

    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._embeddings = embeddings
        self._vector_store = vector_store

    @classmethod
    def from_settings(cls, settings: Settings) -> "RagRetriever":
        """Build a retriever from the configured embedding and vector providers."""

        return cls(
            embeddings=create_embedding_provider(settings),
            vector_store=create_vector_store(settings),
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        normalized = query.strip()
        if not normalized:
            raise RetrievalError("Retrieval query must not be blank")
        if top_k <= 0:
            raise RetrievalError("top_k must be positive")

        embedding = self._embeddings.embed_query(normalized)
        return self._vector_store.query(embedding, top_k=top_k, where=where)


__all__ = ["RagRetriever", "RetrievalError", "Retriever"]
