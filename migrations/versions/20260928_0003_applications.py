"""phase 1: applications, scores, events

Revision ID: 0003_applications
Revises: 0002_phase1_candidate_job
Create Date: 2026-09-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_applications"
down_revision: str | None = "0002_phase1_candidate_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
NOW = sa.text("now()")
UUID = postgresql.UUID(as_uuid=True)


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", TS, server_default=NOW, nullable=False),
        sa.Column("updated_at", TS, server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "applications",
        *_base(),
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("resume_version_id", UUID,
                  sa.ForeignKey("resume_versions.id", ondelete="SET NULL")),
        sa.Column("cover_note", sa.Text),
        sa.Column("stage", sa.String(16), server_default="new", nullable=False),
        sa.Column("stage_changed_at", TS),
        sa.Column("stage_changed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(16), server_default="platform", nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB),
        sa.UniqueConstraint("job_id", "candidate_user_id", name="uq_application_job_candidate"),
    )
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_candidate_user_id", "applications", ["candidate_user_id"])
    op.create_index("ix_applications_job_stage", "applications", ["job_id", "stage"])

    op.create_table(
        "application_scores",
        *_base(),
        sa.Column("application_id", UUID,
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scoring_version", sa.Integer, server_default="1", nullable=False),
        sa.Column("composite", sa.Numeric(5, 2), nullable=False),
        sa.Column("lexical", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("semantic", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("rules", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("weights", postgresql.JSONB, nullable=False),
        sa.Column("justification", sa.Text),
        sa.Column("evidence", postgresql.JSONB),
        sa.Column("missing_requirements", postgresql.JSONB),
        sa.Column("agent_run_id", UUID, sa.ForeignKey("agent_runs.id", ondelete="SET NULL")),
        sa.UniqueConstraint("application_id", "scoring_version", name="uq_score_app_version"),
    )
    op.create_index("ix_application_scores_application_id", "application_scores",
                    ["application_id"])
    op.create_index("ix_application_scores_app", "application_scores",
                    ["application_id", "scoring_version"])

    op.create_table(
        "application_events",
        *_base(),
        sa.Column("application_id", UUID,
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_type", sa.String(16), server_default="user", nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB),
    )
    op.create_index("ix_application_events_application_id", "application_events",
                    ["application_id"])
    op.create_index("ix_application_events_app_created", "application_events",
                    ["application_id", "created_at"])

    # Candidate profiles get the same full-text treatment as jobs, so lexical matching
    # runs in the database alongside vector similarity (ADR-0003).
    op.execute(
        """
        ALTER TABLE candidate_profiles ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(headline, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(summary, '')), 'B')
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_candidate_profiles_search_vector "
        "ON candidate_profiles USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidate_profiles_search_vector")
    op.execute("ALTER TABLE candidate_profiles DROP COLUMN IF EXISTS search_vector")
    op.drop_table("application_events")
    op.drop_table("application_scores")
    op.drop_table("applications")
