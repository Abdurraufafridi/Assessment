"""ChromaDB persistent vector store."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.logging import get_logger
from app.ingestion.metadata import Metadata, MetadataValue
from app.vectorstore.base import VectorSearchResult, VectorStoreError

logger = get_logger(__name__)


class ChromaVectorStore:
    """Persistent Chroma collection with explicit embeddings and cosine space."""

    def __init__(self, persist_directory: str, collection_name: str) -> None:
        if not collection_name.strip():
            raise VectorStoreError("CHROMA_COLLECTION_NAME must be set")

        self._collection_name = collection_name
        path = Path(persist_directory).expanduser()
        path.mkdir(parents=True, exist_ok=True)

        try:
            self._client = chromadb.PersistentClient(
                path=path,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Unable to open Chroma collection '{collection_name}': {exc}"
            ) from exc

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def upsert_chunks(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, MetadataValue]],
    ) -> None:
        if not ids:
            return
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise VectorStoreError("Vector record collections must have equal lengths")

        try:
            self._collection.upsert(
                ids=list(ids),
                embeddings=cast(Any, [list(vector) for vector in embeddings]),
                documents=list(documents),
                metadatas=[dict(metadata) for metadata in metadatas],
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to upsert vectors: {exc}") from exc

    def query(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        try:
            raw = cast(
                dict[str, Any],
                self._collection.query(
                    query_embeddings=cast(Any, [list(query_embedding)]),
                    n_results=top_k,
                    where=self._build_where(where),
                    include=["documents", "metadatas", "distances"],
                ),
            )
        except Exception as exc:
            raise VectorStoreError(f"Vector query failed: {exc}") from exc

        ids = self._first_result_list(raw.get("ids"))
        documents = self._first_result_list(raw.get("documents"))
        metadatas = self._first_result_list(raw.get("metadatas"))
        distances = self._first_result_list(raw.get("distances"))

        results: list[VectorSearchResult] = []
        for record_id, text, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            distance_value = float(distance)
            results.append(
                VectorSearchResult(
                    id=str(record_id),
                    text=str(text),
                    metadata=self._metadata_dict(metadata),
                    distance=distance_value,
                    score=1.0 - distance_value,
                )
            )
        return results

    def get_document_chunks(self, document_id: str) -> list[VectorSearchResult]:
        try:
            raw = cast(
                dict[str, Any],
                self._collection.get(
                    where={"document_id": document_id},
                    include=["documents", "metadatas"],
                ),
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to read chunks for document '{document_id}': {exc}"
            ) from exc

        ids = raw.get("ids") or []
        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []

        results = [
            VectorSearchResult(
                id=str(record_id),
                text=str(text),
                metadata=self._metadata_dict(metadata),
            )
            for record_id, text, metadata in zip(ids, documents, metadatas, strict=False)
        ]
        return sorted(results, key=lambda result: int(result.metadata.get("chunk_index", 0)))

    def delete_document(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": document_id})
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to delete vectors for document '{document_id}': {exc}"
            ) from exc

    def count(self) -> int:
        try:
            return int(self._collection.count())
        except Exception as exc:
            raise VectorStoreError(f"Failed to count vectors: {exc}") from exc

    @staticmethod
    def _build_where(where: Mapping[str, MetadataValue] | None) -> dict[str, Any] | None:
        """Convert a flat equality filter into a Chroma ``where`` clause."""

        if not where:
            return None
        if len(where) == 1:
            return dict(where)
        return {"$and": [{key: value} for key, value in where.items()]}

    @staticmethod
    def _first_result_list(value: object) -> list[Any]:
        if isinstance(value, list) and value and isinstance(value[0], list):
            return value[0]
        return []

    @staticmethod
    def _metadata_dict(value: object) -> Metadata:
        if not isinstance(value, dict):
            return {}
        return {
            str(key): item
            for key, item in value.items()
            if isinstance(item, (str, int, float, bool))
        }
