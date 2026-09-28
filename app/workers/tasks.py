from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.db.session import SessionFactory
from app.models import AgentRun
from app.services import runs as run_service


async def ping(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Phase 0 exit-gate job: proves enqueue → run → progress → terminal event works.

    Delete once a real agent task exists.
    """
    rid = uuid.UUID(run_id)
    async with SessionFactory() as session:
        run = await session.get(AgentRun, rid)
        if run is None:
            return {"ok": False, "reason": "run not found"}
        try:
            for step, pct in (("starting", 10), ("working", 55), ("finishing", 90)):
                await run_service.mark_progress(session, run, step=step, pct=pct)
                await session.commit()
                await asyncio.sleep(0.4)
            await run_service.mark_succeeded(session, run, output_ref={"pong": True})
            await session.commit()
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001 - the run must record its own failure
            await run_service.mark_failed(session, run, code="internal", message=str(exc))
            await session.commit()
            raise
