"""Shared route dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFound
from app.core.security import CurrentPrincipal, Principal
from app.db.session import get_session
from app.models import User

_pool: ArqRedis | None = None


async def arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def current_user(
    principal: Principal = CurrentPrincipal,
    session: AsyncSession = Depends(get_session),
) -> User:
    """The local mirror row. Absent means the Clerk webhook has not landed yet."""
    user = (
        await session.execute(select(User).where(User.clerk_user_id == principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise NotFound("Your account is still being set up. Try again in a moment.")
    return user


async def current_org_id(principal: Principal = CurrentPrincipal) -> uuid.UUID:
    return uuid.UUID(principal.require_org())


CurrentUser = Annotated[User, Depends(current_user)]
Session = Annotated[AsyncSession, Depends(get_session)]
