from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_db_url(url: str) -> str:
    """Rewrite any Postgres URL so SQLAlchemy uses the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCOUT_", env_file=".env", extra="ignore", populate_by_name=True
    )

    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    database_url: str = Field(alias="DATABASE_URL")
    google_places_api_key: str | None = Field(default=None, alias="GOOGLE_PLACES_API_KEY")
    apify_token: str | None = Field(default=None, alias="APIFY_TOKEN")
    dashboard_token: str | None = Field(default=None, alias="DASHBOARD_TOKEN")

    phase: str = "foundation"
    daily_budget_eur: Decimal = Decimal("3.00")
    run_max_minutes: int = 50
    usd_to_eur: Decimal = Decimal("0.92")
    timezone: str = "Europe/Belgrade"
    director_review: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_db_url(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
