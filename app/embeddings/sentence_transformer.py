"""Local sentence-transformers embedding provider."""

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from app.embeddings.base import EmbeddingConfigurationError, EmbeddingError


@lru_cache(maxsize=2)
def _load_model(model_name: str, device: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingConfigurationError(
            "sentence-transformers is not installed; install project dependencies"
        ) from exc

    try:
        return SentenceTransformer(model_name, device=device)
    except Exception as exc:
        raise EmbeddingConfigurationError(
            f"Unable to load embedding model '{model_name}': {exc}"
        ) from exc


class SentenceTransformerEmbeddingProvider:
    """Embeds text locally with a configurable sentence-transformers model."""

    def __init__(self, model_name: str, *, device: str = "cpu", batch_size: int = 32) -> None:
        if not model_name.strip():
            raise EmbeddingConfigurationError("EMBEDDING_MODEL must be set")
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = _load_model(model_name, device)

        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is None:
            raise EmbeddingConfigurationError(
                f"Embedding model '{model_name}' did not report a vector dimension"
            )
        self._dimension = int(dimension)

    @property
    def provider_name(self) -> str:
        return "sentence_transformers"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = self._model.encode(
                list(texts),
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingError(
                f"Failed to embed {len(texts)} text(s) with '{self._model_name}': {exc}"
            ) from exc
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise EmbeddingError("Embedding provider returned no vector for the query")
        return vectors[0]
