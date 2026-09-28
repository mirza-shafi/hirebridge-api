"""DEV_AUTH removes authentication. The guard that keeps it local is the whole feature."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "database_url": "postgresql+asyncpg://u:p@localhost:5432/db",
    "redis_url": "redis://localhost:6379/0",
}


def test_dev_auth_is_refused_outside_local() -> None:
    for environment in ("staging", "production"):
        with pytest.raises(ValidationError, match="only permitted when ENVIRONMENT=local"):
            Settings(**BASE, dev_auth=True, environment=environment)  # type: ignore[arg-type]


def test_dev_auth_is_allowed_locally() -> None:
    settings = Settings(**BASE, dev_auth=True, environment="local")  # type: ignore[arg-type]
    assert settings.dev_auth is True


def test_clerk_issuer_is_required_when_dev_auth_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # conftest seeds CLERK_ISSUER so the rest of the suite can import the app; clear it
    # here, or pydantic-settings fills the field from the environment and the validator
    # never sees it missing.
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    with pytest.raises(ValidationError, match="CLERK_ISSUER is required"):
        Settings(**BASE, dev_auth=False, environment="local")  # type: ignore[arg-type]


def test_real_auth_configuration_still_validates() -> None:
    settings = Settings(  # type: ignore[arg-type]
        **BASE, environment="production", clerk_issuer="https://x.clerk.accounts.dev"
    )
    assert settings.dev_auth is False
    assert settings.is_production is True
