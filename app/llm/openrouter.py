"""OpenRouter LLM provider."""

from typing import Any

import httpx

from app.llm.base import LLMConfigurationError, LLMRequestError, LLMResponseError


class OpenRouterProvider:
    """Generate text through OpenRouter's OpenAI-compatible chat API."""

    provider_name = "openrouter"

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
            raise LLMConfigurationError("An OpenRouter API key is required")
        if not model.strip():
            raise LLMConfigurationError("An OpenRouter model name is required")
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate one JSON-oriented response from OpenRouter."""

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
        }
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise LLMRequestError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMRequestError(
                f"OpenRouter returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMResponseError("OpenRouter returned a non-JSON response") from exc

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise LLMResponseError("OpenRouter returned no choices")

        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise LLMResponseError("OpenRouter returned an empty response")
        return text.strip()

    def close(self) -> None:
        """Close the underlying HTTP client."""

        self._client.close()
