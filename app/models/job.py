from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class JobStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"
    CLOSED = "closed"


class Job(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_job_org_slug"),
        Index("ix_jobs_org_status", "org_id", "status"),
        Index("ix_jobs_public_board", "status", "published_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220))
    description_raw: Mapped[str] = mapped_column(Text)
    description_structured: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    seniority: Mapped[str | None] = mapped_column(String(32))
    employment_type: Mapped[str | None] = mapped_column(String(32))
    work_mode: Mapped[str | None] = mapped_column(String(16))
    location: Mapped[str | None] = mapped_column(String(160))

    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))

    must_have_skills: Mapped[list[str] | None] = mapped_column(JSONB)
    nice_to_have_skills: Mapped[list[str] | None] = mapped_column(JSONB)
    min_years: Mapped[int | None] = mapped_column(Integer)
    max_years: Mapped[int | None] = mapped_column(Integer)

    # Discriminatory phrasing found by the JD parser. Publishing is blocked while any
    # flag is unresolved (docs/03-agent-specs.md §2).
    red_flags: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.DRAFT.value)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    embedding: Mapped[Any | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(80))

    @property
    def has_unresolved_red_flags(self) -> bool:
        return any(not flag.get("resolved") for flag in (self.red_flags or []))
