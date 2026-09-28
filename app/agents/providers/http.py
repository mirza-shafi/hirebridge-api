"""Shared HTTP behaviour for provider adapters.

Deliberately built on httpx rather than a vendor SDK: the surface needed is small, the app
already depends on httpx, and mapping provider errors onto `TransientProviderError` in one
place is what makes the runner's retry policy behave identically across providers.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.agents.errors import TransientProviderError

RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class ProviderError(RuntimeError):
    """Non-retryable provider failure — a bad request, or a rejected key."""


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise TransientProviderError(f"{type(exc).__name__}: {exc}") from exc

    if response.status_code in RETRYABLE_STATUS:
        raise TransientProviderError(f"HTTP {response.status_code}: {response.text[:300]}")
    if response.status_code >= 400:
        raise ProviderError(f"HTTP {response.status_code}: {response.text[:300]}")

    return response.json()
