from __future__ import annotations

from httpx import AsyncClient


async def test_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unauthenticated_me_is_problem_json(client: AsyncClient) -> None:
    response = await client.get("/v1/me")
    assert response.status_code == 403
    body = response.json()
    assert body["type"].endswith("/forbidden")
    assert "request_id" in body
    assert response.headers["X-Request-ID"]
