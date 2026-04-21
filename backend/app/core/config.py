from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "AI-ассистент врача"

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://aimed:aimed@db:5432/aimed",
        description="Async SQLAlchemy DSN (driver: asyncpg).",
    )
    JWT_SECRET: str = Field(default="change-me-in-local-env")

    # Legacy single-key setting. Kept as a fallback when LLM_API_KEY / ASR_API_KEY
    # are not provided — this preserves the previous OpenAI-only setup.
    OPENAI_API_KEY: str = Field(default="")

    # --- LLM (analysis) ---
    # Any OpenAI-compatible server works: OpenAI itself, LM Studio, Ollama,
    # DeepSeek, Groq, etc. Base URL must include the version segment (usually /v1).
    LLM_API_KEY: str = Field(default="")
    LLM_BASE_URL: str = Field(default="https://api.openai.com/v1")
    LLM_MODEL: str = Field(default="gpt-4o-mini")
    # "json_schema" — strict Structured Outputs (OpenAI, some Groq models).
    # "json_object" — loose JSON mode (LM Studio, Ollama, most open models).
    LLM_JSON_MODE: Literal["json_schema", "json_object"] = Field(default="json_schema")

    # --- ASR (speech-to-text) ---
    # OpenAI-compatible Whisper endpoint. Examples:
    #   OpenAI:                 https://api.openai.com/v1
    #   faster-whisper-server:  http://whisper:8000/v1 (in docker-compose)
    #   Groq:                   https://api.groq.com/openai/v1
    ASR_API_KEY: str = Field(default="")
    ASR_BASE_URL: str = Field(default="https://api.openai.com/v1")
    ASR_MODEL: str = Field(default="whisper-1")

    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def resolved_llm_api_key(self) -> str:
        """Return LLM key, falling back to legacy OPENAI_API_KEY if unset."""
        return self.LLM_API_KEY or self.OPENAI_API_KEY

    @property
    def resolved_asr_api_key(self) -> str:
        """Return ASR key, falling back to legacy OPENAI_API_KEY if unset."""
        return self.ASR_API_KEY or self.OPENAI_API_KEY


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
