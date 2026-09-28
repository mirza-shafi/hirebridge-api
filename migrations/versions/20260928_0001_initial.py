"""initial: orgs, users, memberships, agent_runs, audit_logs + pgvector

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-28
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", TS, server_default=NOW, nullable=False),
        sa.Column("updated_at", TS, server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "organizations",
        *_base_columns(),
        sa.Column("clerk_org_id", sa.String(64), unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("website", sa.String(255)),
        sa.Column("plan", sa.String(32), server_default="starter", nullable=False),
        sa.Column("monthly_token_budget", sa.BigInteger, server_default="5000000", nullable=False),
        sa.Column("tokens_used_this_period", sa.BigInteger, server_default="0", nullable=False),
    )
    op.create_index("ix_organizations_clerk_org_id", "organizations", ["clerk_org_id"])

    op.create_table(
        "users",
        *_base_columns(),
        sa.Column("clerk_user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(200)),
        sa.Column("type", sa.String(20), server_default="candidate", nullable=False),
        sa.Column("last_active_at", TS),
    )

    op.create_table(
        "memberships",
        *_base_columns(),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), server_default="recruiter", nullable=False),
        sa.Column("accepted_at", TS),
        sa.UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "agent_runs",
        *_base_columns(),
        sa.Column("agent", sa.String(48), nullable=False),
        sa.Column("prompt_version", sa.String(16), server_default="v1", nullable=False),
        sa.Column("model", sa.String(80)),
        sa.Column("provider", sa.String(32)),
        sa.Column("subject_type", sa.String(48)),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("step", sa.String(48)),
        sa.Column("progress", sa.Integer, server_default="0", nullable=False),
        sa.Column("input_ref", postgresql.JSONB),
        sa.Column("output_ref", postgresql.JSONB),
        sa.Column("input_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("attempt", sa.Integer, server_default="1", nullable=False),
        sa.Column("validator_status", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("finished_at", TS),
    )
    op.create_index("ix_agent_runs_agent_created", "agent_runs", ["agent", "created_at"])
    op.create_index("ix_agent_runs_org_created", "agent_runs", ["org_id", "created_at"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_subject_id", "agent_runs", ["subject_id"])
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])

    op.create_table(
        "audit_logs",
        *_base_columns(),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(48), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("payload", postgresql.JSONB),
    )
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["org_id", "created_at"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("agent_runs")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
