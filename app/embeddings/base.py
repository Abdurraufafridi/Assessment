"""Embedding provider interface."""

from collections.abc import Sequence
from typing import Protocol


class EmbeddingError(Exception):
    """Base exception for embedding failures."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the embedding provider is not configured correctly."""


class EmbeddingProvider(Protocol):
    """Provider-neutral interface for document and query embeddings."""

    @property
    def provider_name(self) -> str:
        """Stable provider identifier recorded with ingestion metadata."""

    @property
    def model_name(self) -> str:
        """Identifier of the loaded embedding model."""

    @property
    def dimension(self) -> int:
        """Length of every embedding vector produced by this provider."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of document texts."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
