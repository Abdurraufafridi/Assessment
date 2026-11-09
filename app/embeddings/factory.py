"""Embedding provider factory."""

from app.core.config import Settings
from app.embeddings.base import EmbeddingConfigurationError, EmbeddingProvider
from app.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Build the configured embedding provider."""

    if settings.embedding_provider == "sentence_transformers":
        if not settings.embedding_model:
            raise EmbeddingConfigurationError(
                "EMBEDDING_MODEL must be set for the sentence_transformers provider"
            )
        return SentenceTransformerEmbeddingProvider(
            settings.embedding_model,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
        )

    raise EmbeddingConfigurationError(
        f"Unsupported embedding provider '{settings.embedding_provider}'"
    )
