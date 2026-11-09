"""Tests for LLM provider request/response adapters."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.llm.base import LLMConfigurationError, LLMRequestError, LLMResponseError
from app.llm.factory import create_llm_provider
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.llm.openrouter import OpenRouterProvider

pytestmark = pytest.mark.unit


def test_gemini_provider_sends_json_request_and_extracts_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        assert request.headers["x-goog-api-key"] == "test-key"
        payload = json.loads(request.content)
        assert payload["systemInstruction"]["parts"][0]["text"] == "system"
        assert payload["contents"][0]["parts"][0]["text"] == "user"
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GeminiProvider(
        api_key="test-key",
        model="models/gemini-test",
        base_url="https://example.test/v1beta",
        timeout_seconds=5,
        temperature=0,
        max_output_tokens=512,
        client=client,
    )

    try:
        assert provider.generate(system_prompt="system", user_prompt="user") == '{"ok": true}'
        assert provider.provider_name == "gemini"
        assert provider.model_name == "gemini-test"
    finally:
        provider.close()


def test_gemini_provider_raises_on_http_and_empty_response() -> None:
    def error_handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, text="unavailable")

    error_client = httpx.Client(transport=httpx.MockTransport(error_handler))
    error_provider = GeminiProvider(
        api_key="test-key",
        model="gemini-test",
        base_url="https://example.test/v1beta",
        timeout_seconds=5,
        temperature=0,
        max_output_tokens=512,
        client=error_client,
    )
    try:
        with pytest.raises(LLMRequestError, match="HTTP 503"):
            error_provider.generate(system_prompt="system", user_prompt="user")
    finally:
        error_provider.close()

    def empty_handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"candidates": []})

    empty_client = httpx.Client(transport=httpx.MockTransport(empty_handler))
    empty_provider = GeminiProvider(
        api_key="test-key",
        model="gemini-test",
        base_url="https://example.test/v1beta",
        timeout_seconds=5,
        temperature=0,
        max_output_tokens=512,
        client=empty_client,
    )
    try:
        with pytest.raises(LLMResponseError, match="no candidates"):
            empty_provider.generate(system_prompt="system", user_prompt="user")
    finally:
        empty_provider.close()


def test_ollama_provider_sends_chat_request_and_extracts_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "llama-test"
        assert payload["messages"][0] == {"role": "system", "content": "system"}
        assert payload["messages"][1] == {"role": "user", "content": "user"}
        assert payload["format"] == "json"
        return httpx.Response(200, json={"message": {"content": '{"ok": true}'}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        model="llama-test",
        base_url="http://localhost:11434/",
        timeout_seconds=5,
        temperature=0,
        max_output_tokens=512,
        client=client,
    )

    try:
        assert provider.generate(system_prompt="system", user_prompt="user") == '{"ok": true}'
        assert provider.provider_name == "ollama"
    finally:
        provider.close()


def test_openrouter_provider_sends_chat_request_and_extracts_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert payload["messages"][0] == {"role": "system", "content": "system"}
        assert payload["messages"][1] == {"role": "user", "content": "user"}
        assert "response_format" not in payload
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(
        api_key="test-key",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=5,
        temperature=0,
        max_output_tokens=512,
        client=client,
    )

    try:
        assert provider.generate(system_prompt="system", user_prompt="user") == '{"ok": true}'
        assert provider.provider_name == "openrouter"
    finally:
        provider.close()


def test_llm_factory_builds_configured_provider() -> None:
    gemini = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="gemini",
            gemini_api_key="test-key",
            gemini_model="gemini-test",
        )
    )
    assert isinstance(gemini, GeminiProvider)
    gemini.close()

    openrouter = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="openrouter",
            openrouter_api_key="test-key",
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        )
    )
    assert isinstance(openrouter, OpenRouterProvider)
    openrouter.close()

    ollama = create_llm_provider(
        Settings(
            _env_file=None,
            llm_provider="ollama",
            ollama_model="llama-test",
        )
    )
    assert isinstance(ollama, OllamaProvider)
    ollama.close()


def test_llm_factory_requires_provider_credentials() -> None:
    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="gemini",
                gemini_api_key=None,
                gemini_model="gemini-test",
            )
        )

    with pytest.raises(LLMConfigurationError, match="GEMINI_MODEL"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="gemini",
                gemini_api_key="test-key",
                gemini_model=None,
            )
        )

    with pytest.raises(LLMConfigurationError, match="OPENROUTER_API_KEY"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="openrouter",
                openrouter_api_key=None,
                openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            )
        )

    with pytest.raises(LLMConfigurationError, match="OPENROUTER_MODEL"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="openrouter",
                openrouter_api_key="test-key",
                openrouter_model=None,
            )
        )

    with pytest.raises(LLMConfigurationError, match="OLLAMA_MODEL"):
        create_llm_provider(
            Settings(
                _env_file=None,
                llm_provider="ollama",
                ollama_model=None,
            )
        )
