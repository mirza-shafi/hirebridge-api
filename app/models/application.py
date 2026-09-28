from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.schemas.enums import ApplicationStage


class Application(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_user_id", name="uq_application_job_candidate"),
        Index("ix_applications_job_stage", "job_id", "stage"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    cover_note: Mapped[str | None] = mapped_column(Text)

    stage: Mapped[str] = mapped_column(String(16), default=ApplicationStage.NEW.value)
    stage_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage_changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(16), default="platform")

    # Frozen at apply time. The candidate editing their profile next week must not silently
    # change what the recruiter evaluated.
    profile_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ApplicationScore(Base, UUIDPrimaryKey, Timestamps):
    """Versioned, never overwritten.

    Re-ranking after a weight change writes a new row, so "why was this candidate #3 last
    week?" stays answerable (docs/02-data-model.md §4).
    """

    __tablename__ = "application_scores"
    __table_args__ = (
        UniqueConstraint("application_id", "scoring_version", name="uq_score_app_version"),
        Index("ix_application_scores_app", "application_id", "scoring_version"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    scoring_version: Mapped[int] = mapped_column(Integer, default=1)

    composite: Mapped[float] = mapped_column(Numeric(5, 2))
    lexical: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    semantic: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    rules: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # Generated lazily for the top N plus anyone the recruiter opens — writing 400
    # justifications up front wastes roughly 90% of the spend.
    justification: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    missing_requirements: Mapped[list[str] | None] = mapped_column(JSONB)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )


class ApplicationEvent(Base, UUIDPrimaryKey, Timestamps):
    """Append-only. Product rule 3 lives here: every stage change names a human actor."""

    __tablename__ = "application_events"
    __table_args__ = (Index("ix_application_events_app_created", "application_id", "created_at"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(String(16), default="user")
    event: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
