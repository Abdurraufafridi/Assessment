"""Tests for the RAG retrieval service used by the research agent."""

from collections.abc import Mapping, Sequence

import pytest

from app.ingestion.metadata import MetadataValue
from app.services.retrieval import RagRetriever, RetrievalError
from app.vectorstore.base import VectorSearchResult

pytestmark = pytest.mark.unit


class FakeEmbeddings:
    provider_name = "fake"
    model_name = "fake-embedding"
    dimension = 2

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 2.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [1.0, 2.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.calls: list[tuple[Sequence[float], int, Mapping[str, MetadataValue] | None]] = []

    def upsert_chunks(self, **kwargs: object) -> None:
        del kwargs

    def query(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int = 5,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        self.calls.append((query_embedding, top_k, where))
        return [
            VectorSearchResult(
                id="doc:0000",
                text="Warehouse evidence",
                metadata={"document_id": "doc"},
                score=0.9,
            )
        ]

    def get_document_chunks(self, document_id: str) -> list[VectorSearchResult]:
        del document_id
        return []

    def delete_document(self, document_id: str) -> None:
        del document_id

    def count(self) -> int:
        return 1


def test_rag_retriever_embeds_query_and_filters_vector_store() -> None:
    embeddings = FakeEmbeddings()
    vector_store = FakeVectorStore()
    retriever = RagRetriever(embeddings=embeddings, vector_store=vector_store)

    results = retriever.search(
        " warehouse modernization ",
        top_k=3,
        where={"industry": "logistics"},
    )

    assert embeddings.queries == ["warehouse modernization"]
    assert vector_store.calls == [([1.0, 2.0], 3, {"industry": "logistics"})]
    assert results[0].text == "Warehouse evidence"


def test_rag_retriever_rejects_blank_queries() -> None:
    retriever = RagRetriever(embeddings=FakeEmbeddings(), vector_store=FakeVectorStore())

    with pytest.raises(RetrievalError, match="must not be blank"):
        retriever.search("   ")
