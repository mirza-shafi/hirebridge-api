"""Tenant-scoped repository base.

Every employer-owned query goes through here. Route handlers must not build their own
org filters — forgetting one is a cross-tenant data leak, so the scoping lives in one place.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    model: type[ModelT]
    org_scoped: bool = True

    def __init__(self, session: AsyncSession, org_id: uuid.UUID | None = None) -> None:
        if self.org_scoped and org_id is None:
            raise ValueError(f"{type(self).__name__} requires an org_id.")
        self.session = session
        self.org_id = org_id

    def _scoped(self) -> Select[tuple[ModelT]]:
        stmt = select(self.model)
        if self.org_scoped:
            stmt = stmt.where(self.model.org_id == self.org_id)  # type: ignore[attr-defined]
        return stmt

    async def get(self, obj_id: uuid.UUID) -> ModelT | None:
        stmt = self._scoped().where(self.model.id == obj_id)  # type: ignore[attr-defined]
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_404(self, obj_id: uuid.UUID) -> ModelT:
        obj = await self.get(obj_id)
        if obj is None:
            # Deliberately 404 rather than 403 for another tenant's row.
            raise NotFound(f"{self.model.__name__} not found.")
        return obj

    async def list(self, limit: int = 25, **filters: Any) -> list[ModelT]:
        stmt = self._scoped().limit(limit)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        return list((await self.session.execute(stmt)).scalars())

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj
