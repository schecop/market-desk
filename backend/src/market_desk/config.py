"""Application settings, read from environment variables (and `.env` locally)."""

from functools import lru_cache
from typing import Any

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env at the repo root (run from backend/) or in the current directory; real env vars win
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Default matches docker-compose.yml so local dev works without a .env file
    database_url: str = "postgresql+psycopg://market_desk:market_desk@localhost:5432/market_desk"

    # Optional so the app and CI start without it; the Cala client fails clearly if it's missing.
    # SecretStr masks the value in repr/logs; read it with .get_secret_value().
    cala_api_key: SecretStr | None = None

    # mode="before": runs on the raw value, before Pydantic converts it to SecretStr
    @field_validator("cala_api_key", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        # An empty or whitespace-only string means "not configured"
        if isinstance(v, str) and not v.strip():
            return None
        return v


@lru_cache
def get_settings() -> Settings:
    """Build settings once and reuse them (env is read at first call)."""
    return Settings()
