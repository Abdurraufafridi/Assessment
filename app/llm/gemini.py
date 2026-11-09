"""Google Gemini LLM provider."""

from typing import Any

import httpx

from app.llm.base import LLMConfigurationError, LLMRequestError, LLMResponseError


class GeminiProvider:
    """Generate text with the Gemini generateContent REST API."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        temperature: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError("A Gemini API key is required")
        if not model.strip():
            raise LLMConfigurationError("A Gemini model name is required")
        self._api_key = api_key
        self._model = model.strip().removeprefix("models/")
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate one JSON-oriented response from Gemini."""

        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": self._max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        try:
            response = self._client.post(
                f"{self._base_url}/models/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise LLMRequestError(f"Gemini request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMRequestError(
                f"Gemini returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMResponseError("Gemini returned a non-JSON response") from exc

        candidates = data.get("candidates") if isinstance(data, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise LLMResponseError("Gemini returned no candidates")

        first = candidates[0]
        content = first.get("content") if isinstance(first, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise LLMResponseError("Gemini returned no response parts")

        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
        if not text:
            raise LLMResponseError("Gemini returned an empty response")
        return text

    def close(self) -> None:
        """Close the underlying HTTP client."""

        self._client.close()
