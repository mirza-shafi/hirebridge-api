"""Shared task plumbing.

An `AgentFailed` has already been recorded on the run by the runner, so it must not be
overwritten here. Any *other* exception is a bug in the task itself, and the run would
otherwise sit at `running` forever — which is worse than a visible failure, because the SSE
stream never terminates and the user's page waits indefinitely.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.errors import AgentFailed
from app.core.logging import run_id_var
from app.db.session import SessionFactory
from app.models import AgentRun
from app.services import runs as run_service

log = logging.getLogger("hirebridge.worker")


class RunNotFound(RuntimeError):
    pass


@asynccontextmanager
async def task_run(run_id: str) -> AsyncIterator[tuple[AsyncSession, AgentRun]]:
    rid = uuid.UUID(run_id)
    token = run_id_var.set(run_id)
    try:
        async with SessionFactory() as session:
            run = await session.get(AgentRun, rid)
            if run is None:
                raise RunNotFound(f"Run {run_id} not found.")
            try:
                yield session, run
                await session.commit()
            except AgentFailed:
                # The runner already wrote the failure and published the terminal event.
                await session.commit()
                raise
            except Exception as exc:
                log.exception("Unhandled error in task for run %s", run_id)
                await session.rollback()
                await _record_unexpected_failure(rid, exc)
                raise
    finally:
        run_id_var.reset(token)


async def _record_unexpected_failure(run_id: uuid.UUID, exc: Exception) -> None:
    """Fresh session: the original one was rolled back and cannot be reused."""
    async with SessionFactory() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:
            return
        await run_service.mark_failed(
            session, run, code="internal", message=f"{type(exc).__name__}: {exc}"
        )
        await session.commit()
