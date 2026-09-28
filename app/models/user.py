from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, Timestamps):
    """Local mirror of the Clerk user, so other tables have something to key on."""

    __tablename__ = "users"

    clerk_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20), default="candidate")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), default="recruiter")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
