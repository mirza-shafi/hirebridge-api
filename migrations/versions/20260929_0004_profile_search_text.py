"""candidate search_vector must cover the facts, not just the headline

Revision ID: 0004_profile_search_text
Revises: 0003_applications
Create Date: 2026-09-29

The original generated column indexed only `headline` and `summary`. Everything that
actually describes a candidate — job titles, employers, bullets, skills — lives in
`profile_facts`, so the lexical half of the ranking scored almost nothing and rewarded
whoever happened to put a keyword in their headline. `search_text` is a denormalised
corpus of the facts, refreshed whenever they change.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_profile_search_text"
down_revision: str | None = "0003_applications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidate_profiles_search_vector")
    op.execute("ALTER TABLE candidate_profiles DROP COLUMN IF EXISTS search_vector")

    op.add_column("candidate_profiles", sa.Column("search_text", sa.Text(), nullable=True))

    op.execute(
        """
        ALTER TABLE candidate_profiles ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(headline, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(search_text, '')), 'B')
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
    op.drop_column("candidate_profiles", "search_text")
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
