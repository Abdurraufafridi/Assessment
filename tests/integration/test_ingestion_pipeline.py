"""Integration tests for the full ingestion pipeline with a test embedding."""

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.db.database import Database
from app.db.models.document import IngestionStatus
from app.ingestion.chunking import ChunkingConfig, TextChunker
from app.ingestion.errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    IngestionError,
    UnsupportedDocumentTypeError,
)
from app.ingestion.pipeline import IngestionOutcome, IngestionPipeline
from app.repositories.documents import DocumentRepository
from app.vectorstore.chroma import ChromaVectorStore

pytestmark = pytest.mark.integration


class KeywordEmbeddingProvider:
    """Deterministic test double. Not used in production."""

    _KEYWORDS = ("inventory", "warehouse", "healthcare", "patient")

    @property
    def provider_name(self) -> str:
        return "test_keyword"

    @property
    def model_name(self) -> str:
        return "test-keyword-v1"

    @property
    def dimension(self) -> int:
        return len(self._KEYWORDS)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        lowered = text.lower()
        counts = [float(lowered.count(keyword)) for keyword in self._KEYWORDS]
        norm = math.sqrt(sum(value * value for value in counts))
        if norm == 0:
            return [1.0 / math.sqrt(self.dimension)] * self.dimension
        return [value / norm for value in counts]


@pytest.fixture
def pipeline(
    database: Database, tmp_path: Path
) -> tuple[IngestionPipeline, KeywordEmbeddingProvider, ChromaVectorStore]:
    provider = KeywordEmbeddingProvider()
    vector_store = ChromaVectorStore(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_chunks",
    )
    instance = IngestionPipeline(
        database=database,
        embeddings=provider,
        vector_store=vector_store,
        chunker=TextChunker(
            ChunkingConfig(
                chunk_size=200,
                chunk_overlap=30,
                min_chunk_size=50,
                boundary_search_chars=50,
            )
        ),
    )
    return instance, provider, vector_store


def test_pipeline_ingests_chunks_and_enables_metadata_filtering(
    pipeline: tuple[IngestionPipeline, KeywordEmbeddingProvider, ChromaVectorStore],
    database: Database,
    tmp_path: Path,
) -> None:
    instance, provider, vector_store = pipeline
    retail = tmp_path / "proposal_retail_upload.txt"
    retail.write_text(
        "Inventory visibility across warehouse locations is the core problem. "
        "The team needs real time stock information in one place.",
        encoding="utf-8",
    )
    healthcare = tmp_path / "proposal_healthcare_upload.txt"
    healthcare.write_text(
        "Healthcare patient records and clinical workflows are fragmented. "
        "Patient data needs secure integration.",
        encoding="utf-8",
    )

    retail_result = instance.ingest_file(
        retail, metadata={"industry": "retail", "proposal_type": "past_proposal"}
    )
    healthcare_result = instance.ingest_file(
        healthcare, metadata={"industry": "healthcare", "proposal_type": "past_proposal"}
    )

    assert retail_result.status == IngestionOutcome.COMPLETED
    assert healthcare_result.status == IngestionOutcome.COMPLETED
    assert retail_result.chunk_count >= 1
    assert healthcare_result.chunk_count >= 1
    assert vector_store.count() == retail_result.chunk_count + healthcare_result.chunk_count

    query = provider.embed_query("warehouse inventory stock visibility")
    unfiltered = vector_store.query(query, top_k=3)
    assert unfiltered
    assert unfiltered[0].metadata["industry"] == "retail"

    filtered = vector_store.query(query, top_k=3, where={"industry": "healthcare"})
    assert filtered
    assert all(result.metadata["industry"] == "healthcare" for result in filtered)

    combined_filter = vector_store.query(
        query,
        top_k=3,
        where={"industry": "retail", "proposal_type": "past_proposal"},
    )
    assert combined_filter
    assert all(result.metadata["industry"] == "retail" for result in combined_filter)

    by_document = vector_store.query(
        query, top_k=3, where={"document_id": retail_result.document_id}
    )
    assert by_document
    assert all(
        result.metadata["document_id"] == retail_result.document_id for result in by_document
    )

    chunks = vector_store.get_document_chunks(retail_result.document_id)
    assert len(chunks) == retail_result.chunk_count
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(
        range(retail_result.chunk_count)
    )
    assert all(chunk.metadata["chunk_count"] == retail_result.chunk_count for chunk in chunks)

    with database.session() as session:
        stored = DocumentRepository(session).get(retail_result.document_id)

    assert stored is not None
    assert stored.status == IngestionStatus.COMPLETED
    assert stored.chunk_count == retail_result.chunk_count
    assert stored.document_metadata["industry"] == "retail"
    assert stored.indexed_at is not None


def test_duplicate_detection_skips_reembedding_unless_forced(
    pipeline: tuple[IngestionPipeline, KeywordEmbeddingProvider, ChromaVectorStore],
    tmp_path: Path,
) -> None:
    instance, _, vector_store = pipeline
    path = tmp_path / "proposal_logistics_upload.txt"
    path.write_text("Warehouse inventory visibility and stock transfers.", encoding="utf-8")

    first = instance.ingest_file(path, metadata={"industry": "logistics"})
    count_after_first = vector_store.count()

    duplicate = instance.ingest_file(path, metadata={"industry": "logistics"})
    assert duplicate.status == IngestionOutcome.DUPLICATE
    assert duplicate.document_id == first.document_id
    assert duplicate.chunk_count == first.chunk_count
    assert vector_store.count() == count_after_first

    forced = instance.ingest_file(path, metadata={"industry": "logistics"}, force=True)
    assert forced.status == IngestionOutcome.COMPLETED
    assert forced.document_id == first.document_id
    assert vector_store.count() == count_after_first


def test_failed_ingestion_is_recorded_as_failed(
    pipeline: tuple[IngestionPipeline, KeywordEmbeddingProvider, ChromaVectorStore],
    database: Database,
    tmp_path: Path,
) -> None:
    instance, _, _ = pipeline
    path = tmp_path / "blank.txt"
    path.write_text("   \n\n\t", encoding="utf-8")
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(EmptyDocumentError):
        instance.ingest_file(path)

    with database.session() as session:
        stored = DocumentRepository(session).get_by_content_hash(content_hash)

    assert stored is not None
    assert stored.status == IngestionStatus.FAILED
    assert stored.error_message is not None
    assert "EmptyDocumentError" in stored.error_message


def test_unsupported_and_oversized_files_are_rejected(
    pipeline: tuple[IngestionPipeline, KeywordEmbeddingProvider, ChromaVectorStore],
    database: Database,
    tmp_path: Path,
) -> None:
    instance, provider, vector_store = pipeline
    unsupported = tmp_path / "data.csv"
    unsupported.write_text("a,b", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentTypeError):
        instance.ingest_file(unsupported)

    tiny_limit_pipeline = IngestionPipeline(
        database=database,
        embeddings=provider,
        vector_store=vector_store,
        chunker=TextChunker(ChunkingConfig(chunk_size=200, chunk_overlap=30)),
        max_file_size_bytes=5,
    )
    too_large = tmp_path / "large.txt"
    too_large.write_text("more than five bytes", encoding="utf-8")

    with pytest.raises(DocumentTooLargeError):
        tiny_limit_pipeline.ingest_file(too_large)


def test_missing_file_is_rejected(
    pipeline: tuple[IngestionPipeline, KeywordEmbeddingProvider, ChromaVectorStore],
    tmp_path: Path,
) -> None:
    instance, _, _ = pipeline

    with pytest.raises(IngestionError, match="does not exist"):
        instance.ingest_file(tmp_path / "missing.txt")
