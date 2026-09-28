"""The ranking query.

Lexical relevance and vector similarity are computed in one statement — the reason pgvector
lives in the primary database rather than a separate vector service (ADR-0003). Python then
adds the structured rules score and the composite, where it is testable without a database.

`ts_rank_cd(..., 32)` normalises to [0, 1), so scaling by 100 is principled rather than a
tuned magic number.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, CandidateProfile, Job, ProfileFact
from app.schemas.enums import ApplicationStage
from app.services.ranking import (
    RankingWeights,
    ScoreResult,
    cover_requirements,
    rank,
    rules_score,
    score,
    similarity_to_score,
)

# Vector similarity is meaningless without both vectors; a candidate whose embedding has not
# been computed yet falls back to lexical and rules rather than scoring zero.
NEUTRAL_SEMANTIC = 50.0


def _query_terms(job: Job) -> str:
    parts = [job.title or ""]
    parts += list(job.must_have_skills or [])
    parts += list(job.nice_to_have_skills or [])
    return " or ".join(p.replace("_", " ") for p in parts if p)


async def fetch_candidates(session: AsyncSession, job: Job) -> list[dict[str, Any]]:
    """Every applicant for the job, with the two database-computed signals.

    Returns all of them. There is no score filter and no LIMIT — the recruiter sees the whole
    list, reordered (product rule 2).
    """
    terms = _query_terms(job)
    tsquery = func.websearch_to_tsquery("english", terms)

    lexical = (
        func.coalesce(func.ts_rank_cd(CandidateProfile.search_vector, tsquery, 32), 0.0)
        * 100.0
    ).cast(Float).label("lexical")

    if job.embedding is not None:
        distance = CandidateProfile.embedding.cosine_distance(job.embedding)
        semantic_distance = distance.label("distance")
    else:
        semantic_distance = func.cast(None, Float).label("distance")

    stmt = (
        select(
            Application.id.label("application_id"),
            CandidateProfile.id.label("profile_id"),
            CandidateProfile.years_experience,
            CandidateProfile.location_city,
            lexical,
            semantic_distance,
        )
        .join(Application, Application.candidate_user_id == CandidateProfile.user_id)
        .where(
            Application.job_id == job.id,
            Application.stage != ApplicationStage.WITHDRAWN.value,
        )
    )

    rows = (await session.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def _skills_by_profile(
    session: AsyncSession, profile_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[str]]:
    """One query for every applicant's skills rather than one per applicant.

    At 400 applicants the per-row version is 400 round trips, which is the difference
    between a rank run taking seconds and taking minutes.
    """
    if not profile_ids:
        return {}

    rows = (
        await session.execute(
            select(ProfileFact.profile_id, ProfileFact.payload).where(
                ProfileFact.profile_id.in_(profile_ids)
            )
        )
    ).all()

    skills: dict[uuid.UUID, set[str]] = {pid: set() for pid in profile_ids}
    for profile_id, payload in rows:
        if not isinstance(payload, dict):
            continue
        skills[profile_id] |= {
            str(s) for s in (payload.get("tech") or []) if s
        }
        if name := payload.get("name"):
            skills[profile_id].add(str(name))
    return skills


async def score_applications(
    session: AsyncSession, job: Job, *, weights: RankingWeights | None = None
) -> list[tuple[uuid.UUID, ScoreResult]]:
    """Score every applicant and return them ordered. Nothing is dropped."""
    candidates = await fetch_candidates(session, job)
    skills = await _skills_by_profile(session, [c["profile_id"] for c in candidates])

    results: list[tuple[uuid.UUID, ScoreResult]] = []
    for row in candidates:
        coverage = cover_requirements(
            skills.get(row["profile_id"], set()),
            must_have=job.must_have_skills,
            nice_to_have=job.nice_to_have_skills,
        )
        breakdown = rules_score(
            years_experience=(
                float(row["years_experience"]) if row["years_experience"] is not None else None
            ),
            min_years=job.min_years,
            max_years=job.max_years,
            job_seniority=job.seniority,
            candidate_city=row["location_city"],
            job_location=job.location,
            work_mode=job.work_mode,
            coverage=coverage,
        )
        semantic = (
            similarity_to_score(float(row["distance"]))
            if row["distance"] is not None
            else NEUTRAL_SEMANTIC
        )
        results.append(
            (
                row["application_id"],
                score(
                    lexical=float(row["lexical"] or 0.0),
                    semantic=semantic,
                    coverage=coverage,
                    breakdown=breakdown,
                    weights=weights,
                ),
            )
        )

    return rank(results)
