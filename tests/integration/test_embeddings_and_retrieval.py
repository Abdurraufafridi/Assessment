"""Real-model embedding and retrieval verification.

These tests download/load the configured sentence-transformers model. Enable
them with ``RUN_EMBEDDING_TESTS=1``.
"""

import os
from pathlib import Path

import pytest

from app.db.database import Database
from app.embeddings.sentence_transformer import SentenceTransformerEmbeddingProvider
from app.ingestion.chunking import ChunkingConfig, TextChunker
from app.ingestion.pipeline import IngestionOutcome, IngestionPipeline
from app.vectorstore.chroma import ChromaVectorStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.embedding,
    pytest.mark.skipif(
        os.getenv("RUN_EMBEDDING_TESTS") != "1",
        reason="set RUN_EMBEDDING_TESTS=1 to run real embedding model tests",
    ),
]

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_real_embeddings_have_expected_dimension_and_semantic_retrieval(tmp_path: Path) -> None:
    provider = SentenceTransformerEmbeddingProvider(MODEL_NAME)
    assert provider.dimension == 384

    database = Database(f"sqlite:///{tmp_path / 'pipeline.db'}")
    database.create_all()
    vector_store = ChromaVectorStore(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="proposal_chunks",
    )
    pipeline = IngestionPipeline(
        database=database,
        embeddings=provider,
        vector_store=vector_store,
        chunker=TextChunker(
            ChunkingConfig(
                chunk_size=600,
                chunk_overlap=100,
                min_chunk_size=100,
                boundary_search_chars=100,
            )
        ),
    )

    try:
        sources = {
            "proposal_logistics.txt": "logistics",
            "proposal_retail2.txt": "retail",
            "proposal_healthcare.txt": "healthcare",
        }
        results = {
            name: pipeline.ingest_file(
                PROJECT_ROOT / name,
                metadata={"industry": industry, "proposal_type": "past_proposal"},
            )
            for name, industry in sources.items()
        }
        transcript = pipeline.ingest_file(PROJECT_ROOT / "client_transcript.txt")

        assert all(result.status == IngestionOutcome.COMPLETED for result in results.values())
        assert transcript.status == IngestionOutcome.COMPLETED
        assert all(result.chunk_count > 0 for result in results.values())
        assert transcript.chunk_count > 0
        assert (
            vector_store.count()
            == sum(result.chunk_count for result in results.values()) + transcript.chunk_count
        )

        for result in results.values():
            chunks = vector_store.get_document_chunks(result.document_id)
            assert len(chunks) == result.chunk_count
            assert all(chunk.metadata["chunk_count"] == result.chunk_count for chunk in chunks)

        healthcare_query = provider.embed_query(
            "hospital patient records and clinical care workflows"
        )
        healthcare_results = vector_store.query(
            healthcare_query, top_k=3, where={"industry": "healthcare"}
        )
        assert healthcare_results
        assert healthcare_results[0].metadata["source_name"] == "proposal_healthcare.txt"
        assert healthcare_results[0].score >= healthcare_results[-1].score

        logistics_query = provider.embed_query(
            "distribution centres, warehouse hubs, and real time inventory visibility"
        )
        logistics_results = vector_store.query(
            logistics_query,
            top_k=3,
            where={"industry": "logistics", "proposal_type": "past_proposal"},
        )
        assert logistics_results
        assert logistics_results[0].metadata["source_name"] == "proposal_logistics.txt"

        document_filtered = vector_store.query(
            logistics_query,
            top_k=3,
            where={"document_id": results["proposal_logistics.txt"].document_id},
        )
        assert document_filtered
        assert all(
            result.metadata["source_name"] == "proposal_logistics.txt"
            for result in document_filtered
        )
    finally:
        database.dispose()
