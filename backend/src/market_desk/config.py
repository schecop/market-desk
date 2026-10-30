"""Application settings, read from environment variables (and `.env` locally)."""

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env at the repo root (run from backend/) or in the current directory; real env vars win
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Default matches docker-compose.yml so local dev works without a .env file
    database_url: str = "postgresql+psycopg://market_desk:market_desk@localhost:5432/market_desk"

    # Optional so the app and CI start without it; the Cala client fails clearly if it's missing.
    # SecretStr masks the value in repr/logs; read it with .get_secret_value().
    cala_api_key: SecretStr | None = None

    # SEC EDGAR requires a User-Agent with a name and a contact email. Not a secret, but it
    # identifies you to the SEC, so it lives in .env too. Optional for the same reason as above.
    edgar_user_agent: str | None = None
    # Development only: where hishel caches EDGAR responses. None (the default) disables the cache.
    edgar_cache_dir: str | None = None

    # Shared secret for signing webhooks, both directions (Standard Webhooks, ADR-0005).
    # Format: "whsec_" + base64 of 24-64 random bytes. Without it, inbound webhooks are refused.
    webhook_signing_secret: SecretStr | None = None
    # Where outbound events go (the n8n webhook node, task 6). Without it, nothing is sent.
    n8n_webhook_url: str | None = None
    # How often the API checks EDGAR for new watchlist filings (task 7). 0 = off: the default,
    # so tests and a plain `make dev` never call EDGAR on their own.
    filing_check_interval_minutes: float = Field(default=0, ge=0)

    # The agent's model calls. Optional so the app starts without it; /chat answers 503 then.
    anthropic_api_key: SecretStr | None = None

    # mode="before": runs on the raw value, before Pydantic converts it to the field's type
    @field_validator(
        "cala_api_key",
        "edgar_user_agent",
        "edgar_cache_dir",
        "webhook_signing_secret",
        "n8n_webhook_url",
        "anthropic_api_key",
        mode="before",
    )
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
