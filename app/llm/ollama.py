"""Local Ollama LLM provider."""

from typing import Any

import httpx

from app.llm.base import LLMConfigurationError, LLMRequestError, LLMResponseError


class OllamaProvider:
    """Generate text with the local Ollama chat API."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout_seconds: float,
        temperature: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip():
            raise LLMConfigurationError("An Ollama model name is required")
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate one JSON-oriented response from Ollama."""

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_output_tokens,
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LLMRequestError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMRequestError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMResponseError("Ollama returned a non-JSON response") from exc

        message = data.get("message") if isinstance(data, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise LLMResponseError("Ollama returned an empty response")
        return text.strip()

    def close(self) -> None:
        """Close the underlying HTTP client."""

        self._client.close()
