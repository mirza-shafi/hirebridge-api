from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.routes._deps import CurrentUser, Session, arq_pool, current_org_id
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models import Application, ApplicationScore, Job, JobStatus
from app.services.idempotency import IdempotencyKey, get_or_create_run
from app.workers.settings import QUEUE_GENERATE, QUEUE_PARSE

router = APIRouter(prefix="/jobs", tags=["jobs"])

OrgId = Annotated[uuid.UUID, Depends(current_org_id)]


class CreateJob(BaseModel):
    description_raw: str = Field(min_length=50)


class ResolveFlag(BaseModel):
    index: int
    resolved: bool = True
    note: str | None = None


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    body: CreateJob, user: CurrentUser, org_id: OrgId, session: Session,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    job = Job(
        org_id=org_id, created_by=user.id, title="Untitled role",
        slug=f"draft-{uuid.uuid4().hex[:8]}", description_raw=body.description_raw,
        status=JobStatus.DRAFT.value,
    )
    session.add(job)
    await session.flush()

    run, created = await get_or_create_run(
        session, agent="jd_parser", principal_user_id=str(user.clerk_user_id),
        idempotency_key=idempotency_key, user_id=user.id, org_id=org_id,
        subject_type="job", subject_id=job.id,
    )
    await session.commit()

    if created:
        pool = await arq_pool()
        await pool.enqueue_job("parse_job", str(run.id), str(job.id), _queue_name=QUEUE_PARSE)
    return {
        "job_id": str(job.id), "run_id": str(run.id), "status": "queued",
        "events": f"/v1/runs/{run.id}/events",
    }


@router.get("")
async def list_jobs(
    org_id: OrgId, session: Session,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[dict[str, Any]]:
    stmt = select(Job).where(Job.org_id == org_id).order_by(Job.created_at.desc())
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)
    jobs = (await session.execute(stmt)).scalars().all()

    counts = dict(
        (
            await session.execute(
                select(Application.job_id, func.count(Application.id))
                .where(Application.job_id.in_([j.id for j in jobs]))
                .group_by(Application.job_id)
            )
        ).all()
    ) if jobs else {}

    return [
        {
            "id": str(j.id), "title": j.title, "slug": j.slug, "status": j.status,
            "seniority": j.seniority, "applicants": counts.get(j.id, 0),
            "red_flags": len(j.red_flags or []),
            "unresolved_red_flags": j.has_unresolved_red_flags,
        }
        for j in jobs
    ]


async def _org_job(session: Session, job_id: uuid.UUID, org_id: uuid.UUID) -> Job:  # type: ignore[valid-type]
    job = await session.get(Job, job_id)
    # 404 rather than 403 for another org's job: a 403 would confirm it exists.
    if job is None or job.org_id != org_id:
        raise NotFound("Job not found.")
    return job


@router.post("/{job_id}/red-flags/resolve")
async def resolve_red_flag(
    job_id: uuid.UUID, body: ResolveFlag, org_id: OrgId, session: Session
) -> dict[str, Any]:
    job = await _org_job(session, job_id, org_id)
    flags = list(job.red_flags or [])
    if not 0 <= body.index < len(flags):
        raise NotFound("Flag not found.")
    flags[body.index] = {**flags[body.index], "resolved": body.resolved, "note": body.note}
    job.red_flags = flags
    return {"unresolved": job.has_unresolved_red_flags}


@router.post("/{job_id}/publish")
async def publish(job_id: uuid.UUID, org_id: OrgId, session: Session) -> dict[str, Any]:
    """Blocked while discriminatory phrasing is unresolved.

    The employer must edit or explicitly dismiss each flag — the point is that they see it,
    not that we quietly fix their wording.
    """
    job = await _org_job(session, job_id, org_id)
    if job.has_unresolved_red_flags:
        raise Unprocessable(
            "This posting contains wording that may exclude qualified candidates. "
            "Edit or dismiss each flag before publishing.",
            red_flags=[f for f in (job.red_flags or []) if not f.get("resolved")],
        )
    if not job.must_have_skills:
        raise Unprocessable("The job description has not finished processing yet.")

    job.status = JobStatus.PUBLISHED.value
    job.published_at = datetime.now(UTC)
    return {"id": str(job.id), "status": job.status, "slug": job.slug}


@router.post("/{job_id}/rank", status_code=status.HTTP_202_ACCEPTED)
async def rank_applicants(
    job_id: uuid.UUID, user: CurrentUser, org_id: OrgId, session: Session,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    job = await _org_job(session, job_id, org_id)
    run, created = await get_or_create_run(
        session, agent="ranker_justifier", principal_user_id=str(user.clerk_user_id),
        idempotency_key=idempotency_key, user_id=user.id, org_id=org_id,
        subject_type="job", subject_id=job.id,
    )
    await session.commit()

    if created:
        pool = await arq_pool()
        await pool.enqueue_job("rank_job", str(run.id), str(job.id), _queue_name=QUEUE_GENERATE)
    return {"run_id": str(run.id), "events": f"/v1/runs/{run.id}/events"}


@router.get("/{job_id}/applications")
async def list_applicants(
    job_id: uuid.UUID,
    org_id: OrgId,
    session: Session,
    sort: Literal["rank", "recent"] = "rank",
    stage: str | None = None,
) -> dict[str, Any]:
    """Every applicant, always.

    There is no `min_score` parameter and there will not be one: `sort` changes the order,
    nothing is hidden (docs/00-product-brief.md §8 rule 2). The capability is absent rather
    than merely discouraged.
    """
    job = await _org_job(session, job_id, org_id)

    stmt = select(Application).where(Application.job_id == job.id)
    if stage:
        stmt = stmt.where(Application.stage == stage)
    applications = (await session.execute(stmt)).scalars().all()

    latest_version = (
        await session.execute(
            select(func.max(ApplicationScore.scoring_version)).where(
                ApplicationScore.application_id.in_([a.id for a in applications])
            )
        )
    ).scalar_one_or_none() if applications else None

    scores: dict[uuid.UUID, ApplicationScore] = {}
    if latest_version is not None:
        rows = (
            await session.execute(
                select(ApplicationScore).where(
                    ApplicationScore.application_id.in_([a.id for a in applications]),
                    ApplicationScore.scoring_version == latest_version,
                )
            )
        ).scalars().all()
        scores = {row.application_id: row for row in rows}

    items = [
        {
            "application_id": str(a.id),
            "stage": a.stage,
            "applied_at": a.created_at,
            "score": (
                {
                    "composite": float(s.composite),
                    "lexical": float(s.lexical),
                    "semantic": float(s.semantic),
                    "rules": float(s.rules),
                    "justification": s.justification,
                    "matched": s.evidence or [],
                    "missing": s.missing_requirements or [],
                    "scoring_version": s.scoring_version,
                }
                if (s := scores.get(a.id))
                else None
            ),
        }
        for a in applications
    ]

    if sort == "rank":
        # Unscored applicants sort last but are never dropped.
        items.sort(key=lambda i: (i["score"] or {}).get("composite", -1), reverse=True)
    else:
        items.sort(key=lambda i: i["applied_at"], reverse=True)

    return {"total": len(items), "ranked": latest_version is not None, "data": items}
