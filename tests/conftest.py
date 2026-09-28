"""Shared fixtures.

Every import of the web stack happens *inside* a fixture, not at module scope. A release-gate
suite (the fabrication validator, the scoring allowlist) must be runnable without a database,
a Redis connection, or a populated environment — if collecting the tests requires booting the
app, the gate is harder to run than it should be, and a hard-to-run gate gets skipped.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

    from app.agents.llm import FakeLLMClient
    from app.core.security import Principal


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    from app.agents.llm import FakeLLMClient

    return FakeLLMClient()


@pytest.fixture
def principal() -> Principal:
    from app.core.security import Principal

    return Principal(user_id="user_test", email="test@example.com", org_id=None, role="candidate")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(principal: Any) -> AsyncIterator[AsyncClient]:
    """Client with auth bypassed — the token path itself is covered separately."""
    from httpx import ASGITransport, AsyncClient

    from app.core.security import current_principal
    from app.main import app

    async def _override() -> Any:
        return principal

    app.dependency_overrides[current_principal] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
