from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Organization(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "organizations"

    clerk_org_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(32), default="starter")

    monthly_token_budget: Mapped[int] = mapped_column(BigInteger, default=5_000_000)
    tokens_used_this_period: Mapped[int] = mapped_column(BigInteger, default=0)
