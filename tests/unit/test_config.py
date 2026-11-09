"""Unit tests for environment configuration."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit


def test_database_url_rejects_unsupported_backend() -> None:
    with pytest.raises(ValidationError, match="SQLite or PostgreSQL"):
        Settings(_env_file=None, database_url="mysql://localhost/app")  # type: ignore[call-arg]


@pytest.mark.parametrize("value", ["debug", "warning"])
def test_log_level_is_normalised(value: str) -> None:
    settings = Settings(_env_file=None, log_level=value)  # type: ignore[call-arg]
    assert settings.log_level == value.upper()


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    monkeypatch.setenv("GEMINI_MODEL", "configured-model")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env == "production"
    assert settings.gemini_model == "configured-model"
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "super-secret-value"


def test_secrets_are_masked_in_repr() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        gemini_api_key="super-secret-value",
        slack_bot_token="xoxb-secret",
    )

    rendered = repr(settings)

    assert "super-secret-value" not in rendered
    assert "xoxb-secret" not in rendered
