"""LLM provider factory."""

from app.core.config import Settings
from app.llm.base import LLMConfigurationError, LLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.llm.openrouter import OpenRouterProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Build the configured LLM provider."""

    if settings.llm_provider == "gemini":
        if (
            settings.gemini_api_key is None
            or not settings.gemini_api_key.get_secret_value().strip()
        ):
            raise LLMConfigurationError("GEMINI_API_KEY must be set for the gemini LLM provider")
        if not settings.gemini_model:
            raise LLMConfigurationError("GEMINI_MODEL must be set for the gemini LLM provider")
        return GeminiProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    if settings.llm_provider == "openrouter":
        if (
            settings.openrouter_api_key is None
            or not settings.openrouter_api_key.get_secret_value().strip()
        ):
            raise LLMConfigurationError(
                "OPENROUTER_API_KEY must be set for the openrouter LLM provider"
            )
        if not settings.openrouter_model:
            raise LLMConfigurationError(
                "OPENROUTER_MODEL must be set for the openrouter LLM provider"
            )
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key.get_secret_value(),
            model=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    if settings.llm_provider == "ollama":
        if not settings.ollama_model:
            raise LLMConfigurationError("OLLAMA_MODEL must be set for the ollama LLM provider")
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    raise LLMConfigurationError(f"Unsupported LLM provider '{settings.llm_provider}'")
