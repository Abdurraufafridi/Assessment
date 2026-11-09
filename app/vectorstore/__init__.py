"""Configurable vector storage."""

from app.vectorstore.base import VectorSearchResult, VectorStore, VectorStoreError
from app.vectorstore.factory import create_vector_store

__all__ = ["VectorSearchResult", "VectorStore", "VectorStoreError", "create_vector_store"]
