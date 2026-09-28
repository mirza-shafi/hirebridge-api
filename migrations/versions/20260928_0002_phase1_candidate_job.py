"""phase 1: files, candidate profiles, profile facts, resumes, jobs

Revision ID: 0002_phase1_candidate_job
Revises: 0001_initial
Create Date: 2026-09-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import settings

revision: str = "0002_phase1_candidate_job"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
NOW = sa.text("now()")
UUID = postgresql.UUID(as_uuid=True)

# Sized from config, not hardcoded: a local model (nomic-embed-text is 768) and a
# hosted one (text-embedding-3-small is 1536) differ, and a mismatch between the column
# and the model is silent — pgvector rejects the insert, but only at write time.
EMBEDDING_DIM = settings.embedding_dim


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", TS, server_default=NOW, nullable=False),
        sa.Column("updated_at", TS, server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "files",
        *_base(),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("mime", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("av_scan_status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("retention_until", TS),
    )
    op.create_index("ix_files_owner_user_id", "files", ["owner_user_id"])
    op.create_index("ix_files_org_id", "files", ["org_id"])
    op.create_index("ix_files_checksum_sha256", "files", ["checksum_sha256"])

    op.create_table(
        "candidate_profiles",
        *_base(),
        sa.Column(
            "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("headline", sa.String(200)),
        sa.Column("summary", sa.Text),
        sa.Column("location_city", sa.String(120)),
        sa.Column("years_experience", sa.Numeric(4, 1)),
        sa.Column("open_to_work", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("preferred_roles", postgresql.JSONB),
        sa.Column("completeness_score", sa.Integer, server_default="0", nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("embedding_model", sa.String(80)),
        sa.Column("embedding_updated_at", TS),
    )

    op.create_table(
        "resumes",
        *_base(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(120), server_default="My CV", nullable=False),
        sa.Column("is_base", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("source_file_id", UUID, sa.ForeignKey("files.id", ondelete="SET NULL")),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])

    op.create_table(
        "profile_facts",
        *_base(),
        sa.Column(
            "profile_id", UUID,
            sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("source", sa.String(24), server_default="parsed_resume", nullable=False),
        sa.Column("source_resume_id", UUID, sa.ForeignKey("resumes.id", ondelete="SET NULL")),
        sa.Column("confidence", sa.Numeric(3, 2), server_default="1.0", nullable=False),
        sa.Column("verified_by_user", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("position", sa.Integer, server_default="0", nullable=False),
    )
    op.create_index("ix_profile_facts_profile_id", "profile_facts", ["profile_id"])
    op.create_index("ix_profile_facts_profile_kind", "profile_facts", ["profile_id", "kind"])

    op.create_table(
        "jobs",
        *_base(),
        sa.Column(
            "org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column("description_raw", sa.Text, nullable=False),
        sa.Column("description_structured", postgresql.JSONB),
        sa.Column("seniority", sa.String(32)),
        sa.Column("employment_type", sa.String(32)),
        sa.Column("work_mode", sa.String(16)),
        sa.Column("location", sa.String(160)),
        sa.Column("salary_min", sa.Numeric(12, 2)),
        sa.Column("salary_max", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("must_have_skills", postgresql.JSONB),
        sa.Column("nice_to_have_skills", postgresql.JSONB),
        sa.Column("min_years", sa.Integer),
        sa.Column("max_years", sa.Integer),
        sa.Column("red_flags", postgresql.JSONB),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("published_at", TS),
        sa.Column("closes_at", TS),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("embedding_model", sa.String(80)),
        sa.UniqueConstraint("org_id", "slug", name="uq_job_org_slug"),
    )
    op.create_index("ix_jobs_org_id", "jobs", ["org_id"])
    op.create_index("ix_jobs_org_status", "jobs", ["org_id", "status"])
    op.create_index("ix_jobs_public_board", "jobs", ["status", "published_at"])

    op.create_table(
        "resume_versions",
        *_base(),
        sa.Column("resume_id", UUID, sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column("kind", sa.String(16), server_default="base", nullable=False),
        sa.Column("target_job_id", UUID, sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("target_jd_hash", sa.String(64)),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("citations", postgresql.JSONB),
        sa.Column("template", sa.String(32), server_default="modern", nullable=False),
        sa.Column("pdf_file_id", UUID, sa.ForeignKey("files.id", ondelete="SET NULL")),
        sa.Column("agent_run_id", UUID, sa.ForeignKey("agent_runs.id", ondelete="SET NULL")),
        sa.Column("validator_status", sa.String(32)),
        sa.Column("validator_findings", postgresql.JSONB),
        sa.Column("approved_by_user_at", TS),
        sa.UniqueConstraint("resume_id", "version", name="uq_resume_version"),
    )
    op.create_index("ix_resume_versions_resume_id", "resume_versions", ["resume_id"])

    # Full-text search alongside vectors — one database, hybrid ranking (ADR-0003).
    op.execute(
        """
        ALTER TABLE jobs ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description_raw, '')), 'B')
        ) STORED
        """
    )
    op.execute("CREATE INDEX ix_jobs_search_vector ON jobs USING GIN (search_vector)")

    # HNSW for cosine similarity. Built here while the tables are empty — building these
    # on a populated table needs CONCURRENTLY.
    op.execute(
        "CREATE INDEX ix_jobs_embedding ON jobs "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_candidate_profiles_embedding ON candidate_profiles "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("resume_versions")
    op.drop_table("jobs")
    op.drop_table("profile_facts")
    op.drop_table("resumes")
    op.drop_table("candidate_profiles")
    op.drop_table("files")
