from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.security import CurrentPrincipal, Principal
from app.db.session import get_session
from app.models import User

router = APIRouter(prefix="/me", tags=["me"])


class MeResponse(BaseModel):
    user_id: str
    email: str | None
    org_id: str | None
    role: str
    synced: bool


@router.get("", summary="Current principal (Phase 0 exit gate)")
async def me(
    principal: Principal = CurrentPrincipal,
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    stmt = select(User).where(User.clerk_user_id == principal.user_id)
    local = (await session.execute(stmt)).scalar_one_or_none()
    return MeResponse(
        user_id=principal.user_id,
        email=principal.email,
        org_id=principal.org_id,
        role=principal.role,
        synced=local is not None,
    )
