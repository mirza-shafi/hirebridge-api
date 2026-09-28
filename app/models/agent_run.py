from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED_BUDGET = "aborted_budget"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.ABORTED_BUDGET}


class AgentRun(Base, UUIDPrimaryKey, Timestamps):
    """One row per model invocation.

    This table is simultaneously the audit log, the cost ledger, and the eval dataset.
    No agent call happens without one. Rows are never deleted.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_agent_created", "agent", "created_at"),
        Index("ix_agent_runs_org_created", "org_id", "created_at"),
        Index("ix_agent_runs_status", "status"),
    )

    agent: Mapped[str] = mapped_column(String(48))
    prompt_version: Mapped[str] = mapped_column(String(16), default="v1")
    model: Mapped[str | None] = mapped_column(String(80))
    provider: Mapped[str | None] = mapped_column(String(32))

    subject_type: Mapped[str | None] = mapped_column(String(48))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), default=RunStatus.QUEUED.value)
    step: Mapped[str | None] = mapped_column(String(48))
    progress: Mapped[int] = mapped_column(Integer, default=0)

    input_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, default=1)

    validator_status: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
