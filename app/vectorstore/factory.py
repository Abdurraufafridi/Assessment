"""Vector-store factory."""

from app.core.config import Settings
from app.vectorstore.base import VectorStore, VectorStoreError
from app.vectorstore.chroma import ChromaVectorStore


def create_vector_store(settings: Settings) -> VectorStore:
    """Build the configured persistent vector store."""

    if settings.vector_store_provider == "chroma":
        return ChromaVectorStore(
            persist_directory=settings.chroma_persist_directory,
            collection_name=settings.chroma_collection_name,
        )

    raise VectorStoreError(f"Unsupported vector store provider '{settings.vector_store_provider}'")
