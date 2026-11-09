"""Reusable document ingestion pipeline."""

from app.ingestion.chunking import ChunkingConfig, TextChunk, TextChunker
from app.ingestion.cleaning import clean_text
from app.ingestion.pipeline import IngestionOutcome, IngestionPipeline, IngestionResult

__all__ = [
    "ChunkingConfig",
    "IngestionOutcome",
    "IngestionPipeline",
    "IngestionResult",
    "TextChunk",
    "TextChunker",
    "clean_text",
]
