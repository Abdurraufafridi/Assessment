"""Provider-neutral LLM interface and errors."""

from typing import Protocol


class LLMError(Exception):
    """Base exception for LLM integration failures."""


class LLMConfigurationError(LLMError):
    """Raised when the selected LLM provider is not configured correctly."""


class LLMRequestError(LLMError):
    """Raised when an LLM provider request fails."""


class LLMResponseError(LLMError):
    """Raised when an LLM provider returns an unusable response."""


class LLMProvider(Protocol):
    """Minimal interface required by application agents."""

    @property
    def provider_name(self) -> str:
        """Stable provider identifier recorded in execution metadata."""

    @property
    def model_name(self) -> str:
        """Identifier of the configured model."""

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate a text response for one system/user prompt pair."""
