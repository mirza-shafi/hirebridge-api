"""AgentRun lifecycle + progress fan-out.

Contract (docs/01-architecture.md §4): the API creates the run and enqueues it; the worker
owns every state transition; progress is published to Redis and relayed to the client as SSE.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AgentRun, RunStatus

CHANNEL = "run:{run_id}"
_redis: aioredis.Redis | None = None


def redis_client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def channel_for(run_id: uuid.UUID) -> str:
    return CHANNEL.format(run_id=run_id)


async def create_run(
    session: AsyncSession,
    *,
    agent: str,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    input_ref: dict[str, Any] | None = None,
) -> AgentRun:
    run = AgentRun(
        agent=agent,
        user_id=user_id,
        org_id=org_id,
        subject_type=subject_type,
        subject_id=subject_id,
        idempotency_key=idempotency_key,
        input_ref=input_ref,
        status=RunStatus.QUEUED.value,
    )
    session.add(run)
    await session.flush()
    return run


async def publish(run_id: uuid.UUID, event: str, data: dict[str, Any]) -> None:
    await redis_client().publish(
        channel_for(run_id), json.dumps({"event": event, "data": data})
    )


async def mark_progress(
    session: AsyncSession, run: AgentRun, *, step: str, pct: int
) -> None:
    run.status = RunStatus.RUNNING.value
    run.step = step
    run.progress = pct
    await session.flush()
    await publish(run.id, "progress", {"step": step, "pct": pct})


async def mark_succeeded(
    session: AsyncSession, run: AgentRun, *, output_ref: dict[str, Any]
) -> None:
    run.status = RunStatus.SUCCEEDED.value
    run.progress = 100
    run.output_ref = output_ref
    run.finished_at = datetime.now(UTC)
    await session.flush()
    await publish(run.id, "succeeded", output_ref)


async def mark_failed(
    session: AsyncSession, run: AgentRun, *, code: str, message: str
) -> None:
    run.status = RunStatus.FAILED.value
    run.error_code = code
    run.error_message = message
    run.finished_at = datetime.now(UTC)
    await session.flush()
    await publish(run.id, "failed", {"code": code, "message": message})


async def subscribe(run_id: uuid.UUID) -> AsyncIterator[dict[str, Any]]:
    """Yield events for a run until a terminal one arrives.

    The caller must first reconcile against the stored run: a terminal event fired while the
    client was reconnecting is not replayed here.
    """
    pubsub = redis_client().pubsub()
    await pubsub.subscribe(channel_for(run_id))
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            payload: dict[str, Any] = json.loads(message["data"])
            yield payload
            if payload["event"] in {"succeeded", "failed", "aborted_budget"}:
                return
    finally:
        await pubsub.unsubscribe(channel_for(run_id))
        await pubsub.aclose()
