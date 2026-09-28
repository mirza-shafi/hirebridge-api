from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.llm import FakeLLMClient
from app.core.security import Principal, current_principal
from app.main import app


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def principal() -> Principal:
    return Principal(
        user_id="user_test", email="test@example.com", org_id=None, role="candidate"
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(principal: Principal) -> AsyncIterator[AsyncClient]:
    """Client with auth bypassed — the token path itself is covered separately."""

    async def _override() -> Principal:
        return principal

    app.dependency_overrides[current_principal] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
