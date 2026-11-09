"""Environment-based application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Application settings loaded from environment variables and ``.env``.

    Secrets use :class:`~pydantic.SecretStr` so they are masked in logs and
    representations. Model names and credentials intentionally have no
    application defaults; they must be supplied through the environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Proposal Research Agent"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    database_url: str = "sqlite:///./data/assessment.db"

    llm_provider: Literal["gemini", "openrouter", "ollama"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=2_048, ge=128, le=8_192)

    embedding_provider: Literal["sentence_transformers"] = "sentence_transformers"
    embedding_model: str | None = None
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=32, ge=1, le=512)

    vector_store_provider: Literal["chroma"] = "chroma"
    chroma_persist_directory: str = "./data/chroma"
    chroma_collection_name: str = "proposal_sections"

    ingestion_chunk_size: int = Field(default=1000, ge=100)
    ingestion_chunk_overlap: int = Field(default=150, ge=0)
    ingestion_min_chunk_size: int = Field(default=100, ge=1)
    ingestion_boundary_search_chars: int = Field(default=200, ge=1)
    ingestion_max_file_size_mb: int = Field(default=20, ge=1)

    document_storage_dir: str = "./data/generated"
    document_template_name: str = "professional"
    document_template_path: str | None = None

    slack_bot_token: SecretStr | None = None
    slack_app_token: SecretStr | None = None
    slack_signing_secret: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        url = make_url(value)
        backend = url.get_backend_name()
        if backend not in {"sqlite", "postgresql"}:
            raise ValueError(
                f"DATABASE_URL must use SQLite or PostgreSQL; received backend '{backend}'"
            )
        return value

    @model_validator(mode="after")
    def validate_chunking_settings(self) -> "Settings":
        if self.ingestion_chunk_overlap >= self.ingestion_chunk_size:
            raise ValueError("INGESTION_CHUNK_OVERLAP must be smaller than INGESTION_CHUNK_SIZE")
        if self.ingestion_min_chunk_size > self.ingestion_chunk_size:
            raise ValueError("INGESTION_MIN_CHUNK_SIZE must not exceed INGESTION_CHUNK_SIZE")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""

    return Settings()
