from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.schemas.enums import ValidatorStatus


class Resume(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120), default="My CV")
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )


class ResumeVersion(Base, UUIDPrimaryKey, Timestamps):
    """A rendered CV. `citations` maps each content line to the profile facts behind it."""

    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version", name="uq_resume_version"),)

    resume_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(16), default="base")  # base | tailored

    target_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    target_jd_hash: Mapped[str | None] = mapped_column(String(64))  # for a pasted JD

    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    citations: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    template: Mapped[str] = mapped_column(String(32), default="modern")
    pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )

    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    validator_status: Mapped[str | None] = mapped_column(String(32))
    validator_findings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    # A tailored version cannot attach to an application until the user approves it.
    approved_by_user_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_sendable(self) -> bool:
        return (
            self.validator_status != ValidatorStatus.FAILED.value
            and self.approved_by_user_at is not None
        )
