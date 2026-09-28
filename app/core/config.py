from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Validated at import time so the process fails fast."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Data
    database_url: str
    redis_url: str

    # Auth
    clerk_issuer: str
    clerk_audience: str | None = None
    clerk_webhook_secret: str | None = None

    # LLM (Phase 1)
    llm_provider: Literal["fake", "anthropic", "openai"] = "fake"
    llm_api_key: str | None = None
    model_small: str | None = None
    model_mid: str | None = None
    model_large: str | None = None
    embedding_model: str | None = None
    embedding_dim: int = 1536

    # Storage (Phase 1)
    storage_endpoint: str | None = None
    storage_bucket: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None

    # Budgets
    default_org_monthly_token_budget: int = 5_000_000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
