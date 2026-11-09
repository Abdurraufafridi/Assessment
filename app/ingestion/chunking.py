"""Configurable, boundary-aware text chunking."""

from dataclasses import dataclass

_BOUNDARY_SEPARATORS = ("\n\n", "\n", ". ", "? ", "! ", "; ")


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Character-based chunking parameters.

    Character windows are used instead of token windows so chunking remains
    independent of any specific embedding model.
    """

    chunk_size: int = 1000
    chunk_overlap: int = 150
    min_chunk_size: int = 100
    boundary_search_chars: int = 200

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if not 0 < self.min_chunk_size <= self.chunk_size:
            raise ValueError("min_chunk_size must be between 1 and chunk_size")
        if self.boundary_search_chars <= 0:
            raise ValueError("boundary_search_chars must be positive")


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A chunk of text with its position in the cleaned document."""

    index: int
    text: str
    char_start: int
    char_end: int


class TextChunker:
    """Split text into overlapping chunks, preferring natural boundaries."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()

    def split(self, text: str) -> list[TextChunk]:
        content = text.strip()
        if not content:
            return []

        chunks: list[TextChunk] = []
        start = 0
        length = len(content)

        while start < length:
            end = min(start + self.config.chunk_size, length)

            if end < length and end - start >= self.config.min_chunk_size:
                boundary_start = max(
                    start + self.config.min_chunk_size,
                    end - self.config.boundary_search_chars,
                )
                boundary_end = self._find_boundary(content, boundary_start, end)
                if boundary_end is not None:
                    end = boundary_end

            chunk_text = content[start:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        index=len(chunks),
                        text=chunk_text,
                        char_start=start,
                        char_end=end,
                    )
                )

            if end >= length:
                break

            next_start = end - self.config.chunk_overlap
            start = next_start if next_start > start else end

        return chunks

    @staticmethod
    def _find_boundary(text: str, start: int, end: int) -> int | None:
        best: int | None = None
        for separator in _BOUNDARY_SEPARATORS:
            index = text.rfind(separator, start, end)
            if index == -1:
                continue
            candidate = index + len(separator)
            if best is None or candidate > best:
                best = candidate
        return best
