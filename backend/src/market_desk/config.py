"""Application settings, read from environment variables (and `.env` locally)."""

from functools import lru_cache
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env at the repo root (run from backend/) or in the current directory; real env vars win
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # Default matches docker-compose.yml so local dev works without a .env file
    database_url: str = "postgresql+psycopg://market_desk:market_desk@localhost:5432/market_desk"


@lru_cache
def get_settings() -> Settings:
    """Build settings once and reuse them (env is read at first call)."""
    return Settings()
