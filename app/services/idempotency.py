"""Idempotency for the endpoints that cost money.

Every expensive POST creates an AgentRun. The run row carries the client's
`Idempotency-Key` under a unique index, so replaying a key returns the original run
instead of starting — and paying for — a second one.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun
from app.services.runs import create_run

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Required on any request that triggers paid work. Replaying a key "
        "returns the original run rather than starting a second one.",
        max_length=128,
    ),
]


def scoped_key(user_id: str, agent: str, key: str) -> str:
    """Namespace the client's key so two users cannot collide on the same string."""
    return f"{user_id}:{agent}:{key}"


async def find_run_by_key(session: AsyncSession, key: str) -> AgentRun | None:
    stmt = select(AgentRun).where(AgentRun.idempotency_key == key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_or_create_run(
    session: AsyncSession,
    *,
    agent: str,
    principal_user_id: str,
    idempotency_key: str | None,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    input_ref: dict[str, Any] | None = None,
) -> tuple[AgentRun, bool]:
    """Return (run, created). `created is False` means this was a replay."""
    stored_key: str | None = None
    if idempotency_key:
        stored_key = scoped_key(principal_user_id, agent, idempotency_key)
        if existing := await find_run_by_key(session, stored_key):
            return existing, False

    run = await create_run(
        session,
        agent=agent,
        user_id=user_id,
        org_id=org_id,
        subject_type=subject_type,
        subject_id=subject_id,
        idempotency_key=stored_key,
        input_ref=input_ref,
    )
    return run, True
