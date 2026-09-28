from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.errors import NotFound
from app.core.security import CurrentPrincipal, Principal
from app.db.session import get_session
from app.models import AgentRun, RunStatus
from app.services import runs as run_service
from app.workers.settings import QUEUE_PARSE

router = APIRouter(prefix="/runs", tags=["runs"])

_pool: ArqRedis | None = None


async def arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


class RunResponse(BaseModel):
    run_id: uuid.UUID
    agent: str
    status: str
    step: str | None
    progress: int
    output_ref: dict[str, Any] | None
    error_code: str | None
    error_message: str | None


def _to_response(run: AgentRun) -> RunResponse:
    return RunResponse(
        run_id=run.id,
        agent=run.agent,
        status=run.status,
        step=run.step,
        progress=run.progress,
        output_ref=run.output_ref,
        error_code=run.error_code,
        error_message=run.error_message,
    )


async def _load(session: AsyncSession, run_id: uuid.UUID, principal: Principal) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    # 404 rather than 403 — a 403 would confirm the run exists.
    if run is None:
        raise NotFound("Run not found.")
    return run


@router.post("/ping", status_code=status.HTTP_202_ACCEPTED, summary="Phase 0 exit gate")
async def enqueue_ping(
    principal: Principal = CurrentPrincipal,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    run = await run_service.create_run(session, agent="ping", input_ref={"source": "manual"})
    await session.commit()
    pool = await arq_pool()
    await pool.enqueue_job("ping", str(run.id), _queue_name=QUEUE_PARSE)
    return {
        "run_id": str(run.id),
        "status": run.status,
        "poll": f"/v1/runs/{run.id}",
        "events": f"/v1/runs/{run.id}/events",
    }


@router.get("/{run_id}", summary="Run state — reconcile before trusting SSE")
async def get_run(
    run_id: uuid.UUID,
    principal: Principal = CurrentPrincipal,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    return _to_response(await _load(session, run_id, principal))


@router.get("/{run_id}/events", summary="Progress stream (SSE)")
async def run_events(
    run_id: uuid.UUID,
    request: Request,
    principal: Principal = CurrentPrincipal,
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    run = await _load(session, run_id, principal)

    async def stream() -> AsyncIterator[dict[str, str]]:
        # Terminal already? Emit once and close — a client reconnecting after the fact
        # must not hang waiting for an event that has already been published.
        if RunStatus(run.status).is_terminal:
            yield {"event": run.status, "data": json.dumps(run.output_ref or {})}
            return
        yield {"event": "progress", "data": json.dumps({"step": run.step, "pct": run.progress})}
        async for payload in run_service.subscribe(run_id):
            if await request.is_disconnected():
                break
            yield {"event": payload["event"], "data": json.dumps(payload["data"])}

    return EventSourceResponse(stream())
