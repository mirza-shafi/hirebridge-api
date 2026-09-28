"""Token budget enforcement.

Two ceilings, both from docs/01-architecture.md §4:
  * per-run  — a runaway prompt aborts instead of silently costing money;
  * per-org  — a month's spend is capped; crossing it raises rather than draining the account.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BudgetExceeded
from app.models import Organization

# Rough heuristic for a pre-flight check. The authoritative count comes back from the
# provider after the call; this only stops obviously oversized prompts.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


async def assert_org_within_budget(session: AsyncSession, org_id: uuid.UUID | None) -> None:
    if org_id is None:
        return
    stmt = select(
        Organization.tokens_used_this_period, Organization.monthly_token_budget
    ).where(Organization.id == org_id)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return
    used, budget = row
    if used >= budget:
        raise BudgetExceeded(
            "This organization has reached its monthly token budget. "
            "Usage resets at the start of the next period.",
            used=used,
            budget=budget,
        )


async def record_org_usage(
    session: AsyncSession, org_id: uuid.UUID | None, tokens: int
) -> None:
    if org_id is None or tokens <= 0:
        return
    await session.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(tokens_used_this_period=Organization.tokens_used_this_period + tokens)
    )
