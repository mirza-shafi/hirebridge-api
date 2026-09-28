from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class FactKind(str, enum.Enum):
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILL = "skill"
    PROJECT = "project"
    CERTIFICATION = "certification"
    AWARD = "award"
    PUBLICATION = "publication"
    LANGUAGE = "language"


class FactSource(str, enum.Enum):
    PARSED_RESUME = "parsed_resume"
    USER_ENTERED = "user_entered"
    USER_EDITED = "user_edited"


class CandidateProfile(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    headline: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    location_city: Mapped[str | None] = mapped_column(String(120))
    years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1))
    open_to_work: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_roles: Mapped[list[str] | None] = mapped_column(JSONB)
    completeness_score: Mapped[int] = mapped_column(Integer, default=0)

    embedding: Mapped[Any | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileFact(Base, UUIDPrimaryKey, Timestamps):
    """The grounding table.

    `id` is the `fact_id` that every generated CV line must cite. Nothing reaches a tailored
    CV without a row here — that is what makes the no-fabrication rule mechanically checkable
    rather than a prompt instruction (docs/00-product-brief.md §8 rule 1).
    """

    __tablename__ = "profile_facts"
    __table_args__ = (Index("ix_profile_facts_profile_kind", "profile_id", "kind"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    source: Mapped[str] = mapped_column(String(24), default=FactSource.PARSED_RESUME.value)
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL")
    )
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    verified_by_user: Mapped[bool] = mapped_column(Boolean, default=False)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def needs_review(self) -> bool:
        return float(self.confidence) < 0.7 and not self.verified_by_user
