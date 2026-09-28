from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    # DEV_AUTH replaces token verification with a fixed local identity so the stack
    # runs without a Clerk account. It is refused outside `local` — see the validator
    # below, which is the thing standing between a convenience and an open door.
    dev_auth: bool = False
    dev_auth_token: str = "dev-token"
    clerk_issuer: str = ""
    clerk_audience: str | None = None
    clerk_webhook_secret: str | None = None

    # LLM (Phase 1)
    llm_provider: Literal["fake", "anthropic", "openai", "ollama"] = "fake"
    llm_api_key: str | None = None
    model_small: str | None = None
    model_mid: str | None = None
    model_large: str | None = None
    # Anthropic has no embeddings API, so this is configured independently of
    # llm_provider. Claude for generation + OpenAI/Voyage for embeddings is normal.
    embedding_provider: Literal["fake", "openai", "voyage", "ollama"] = "fake"
    embedding_api_key: str | None = None
    embedding_model: str = "fake-embedding"
    # Must match the model above. The vector columns are sized from this at migration
    # time, so changing it on a populated database needs a backfill.
    embedding_dim: int = 1536

    # Local model server (Ollama). Used when either provider is set to "ollama".
    ollama_base_url: str = "http://localhost:11434"

    # Storage (Phase 1)
    storage_endpoint: str | None = None
    storage_bucket: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    local_storage_path: str = "./.storage"

    # Observability
    sentry_dsn: str | None = None

    # Budgets
    default_org_monthly_token_budget: int = 5_000_000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _guard_dev_auth(self) -> Settings:
        if self.dev_auth and self.environment != "local":
            raise ValueError(
                "DEV_AUTH is only permitted when ENVIRONMENT=local. It bypasses all "
                "authentication; enabling it anywhere else would expose every account."
            )
        if not self.dev_auth and not self.clerk_issuer:
            raise ValueError("CLERK_ISSUER is required unless DEV_AUTH is enabled.")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
