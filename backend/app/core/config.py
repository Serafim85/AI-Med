from functools import lru_cache
from typing import Annotated

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
    OPENAI_API_KEY: str = Field(default="")
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
