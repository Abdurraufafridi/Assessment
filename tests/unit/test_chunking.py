"""Unit tests for chunking behaviour."""

import pytest

from app.ingestion.chunking import ChunkingConfig, TextChunker

pytestmark = pytest.mark.unit


def test_short_text_produces_one_chunk() -> None:
    chunks = TextChunker(ChunkingConfig(chunk_size=100, chunk_overlap=10)).split("Short text.")

    assert len(chunks) == 1
    assert chunks[0].text == "Short text."
    assert chunks[0].index == 0


def test_long_text_respects_size_and_overlap() -> None:
    paragraph = (
        "Inventory visibility across warehouses is critical. "
        "Teams need real time stock information. "
        "Manual reporting consumes hours every week. "
        "Integration with finance systems matters. "
    )
    text = paragraph * 8
    config = ChunkingConfig(
        chunk_size=180,
        chunk_overlap=30,
        min_chunk_size=60,
        boundary_search_chars=50,
    )

    chunks = TextChunker(config).split(text)

    assert len(chunks) > 1
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.text) <= config.chunk_size for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.char_start < previous.char_end
        assert previous.char_end - current.char_start <= config.chunk_overlap


def test_empty_text_produces_no_chunks() -> None:
    assert TextChunker().split("   \n ") == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chunk_size": 100, "chunk_overlap": 100},
        {"chunk_size": 100, "chunk_overlap": -1},
        {"chunk_size": 100, "chunk_overlap": 10, "min_chunk_size": 101},
        {"chunk_size": 100, "chunk_overlap": 10, "boundary_search_chars": 0},
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ChunkingConfig(**kwargs)


def test_chunk_size_equal_to_overlap_plus_one_terminates() -> None:
    chunks = TextChunker(ChunkingConfig(chunk_size=100, chunk_overlap=99, min_chunk_size=10)).split(
        "word " * 100
    )

    assert len(chunks) > 1
