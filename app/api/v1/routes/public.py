"""Public, unauthenticated endpoints.

These back the crawlable pages, so they are cached at the edge and must never leak anything
an employer has not published. A job that is not `published` is a 404 here regardless of
whether it exists.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from app.api.v1.routes._deps import Session
from app.core.errors import NotFound
from app.models import Application, Job, JobStatus, Organization

router = APIRouter(prefix="/public", tags=["public"])

LIST_CACHE = "public, max-age=60, stale-while-revalidate=300"
DETAIL_CACHE = "public, max-age=300, stale-while-revalidate=3600"


def _public_job(job: Job, org: Organization | None) -> dict[str, Any]:
    structured = job.description_structured or {}
    return {
        "id": str(job.id),
        "slug": job.slug,
        "title": job.title,
        "seniority": job.seniority,
        "employment_type": job.employment_type,
        "work_mode": job.work_mode,
        "location": job.location,
        "salary_min": float(job.salary_min) if job.salary_min else None,
        "salary_max": float(job.salary_max) if job.salary_max else None,
        "currency": job.currency,
        "min_years": job.min_years,
        "must_have_skills": job.must_have_skills or [],
        "nice_to_have_skills": job.nice_to_have_skills or [],
        "responsibilities": structured.get("responsibilities", []),
        "requirements": structured.get("requirements", []),
        "benefits": structured.get("benefits", []),
        "team_context": structured.get("team_context"),
        "published_at": job.published_at,
        "closes_at": job.closes_at,
        "status": job.status,
        "company": (
            {"name": org.name, "slug": org.slug, "website": org.website} if org else None
        ),
    }


@router.get("/jobs", summary="Public job board")
async def list_jobs(
    response: Response,
    session: Session,
    q: Annotated[str | None, Query(max_length=200)] = None,
    location: Annotated[str | None, Query(max_length=120)] = None,
    seniority: Annotated[str | None, Query(max_length=32)] = None,
    work_mode: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict[str, Any]:
    stmt = (
        select(Job, Organization)
        .join(Organization, Organization.id == Job.org_id, isouter=True)
        .where(Job.status == JobStatus.PUBLISHED.value)
        .order_by(Job.published_at.desc())
        .limit(limit)
    )
    if q:
        stmt = stmt.where(Job.search_vector.op("@@")(func.websearch_to_tsquery("english", q)))
    if location:
        stmt = stmt.where(Job.location.ilike(f"%{location}%"))
    if seniority:
        stmt = stmt.where(Job.seniority == seniority)
    if work_mode:
        stmt = stmt.where(Job.work_mode == work_mode)

    rows = (await session.execute(stmt)).all()
    response.headers["Cache-Control"] = LIST_CACHE
    return {"data": [_public_job(job, org) for job, org in rows], "next_cursor": None}


@router.get("/jobs/{slug}", summary="Public job detail")
async def job_detail(slug: str, response: Response, session: Session) -> dict[str, Any]:
    """A closed job stays reachable.

    404-ing a URL Google has indexed loses the ranking and dead-ends anyone who saved the
    link. The page renders with a closed banner instead (docs/02-routes-and-screens.md).
    """
    row = (
        await session.execute(
            select(Job, Organization)
            .join(Organization, Organization.id == Job.org_id, isouter=True)
            .where(
                Job.slug == slug,
                Job.status.in_([JobStatus.PUBLISHED.value, JobStatus.CLOSED.value]),
            )
        )
    ).first()
    if row is None:
        raise NotFound("Job not found.")

    job, org = row
    response.headers["Cache-Control"] = DETAIL_CACHE
    return _public_job(job, org)


@router.get("/jobs-index", summary="Slugs for static generation and the sitemap")
async def jobs_index(response: Response, session: Session) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Job.slug, Job.published_at, Job.status).where(
                Job.status.in_([JobStatus.PUBLISHED.value, JobStatus.CLOSED.value])
            )
        )
    ).all()
    response.headers["Cache-Control"] = LIST_CACHE
    return {
        "data": [
            {"slug": slug, "published_at": published_at, "status": status}
            for slug, published_at, status in rows
        ]
    }


@router.get("/orgs/{slug}", summary="Public company page")
async def org_detail(slug: str, response: Response, session: Session) -> dict[str, Any]:
    org = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if org is None:
        raise NotFound("Company not found.")

    jobs = (
        await session.execute(
            select(Job)
            .where(Job.org_id == org.id, Job.status == JobStatus.PUBLISHED.value)
            .order_by(Job.published_at.desc())
        )
    ).scalars().all()

    response.headers["Cache-Control"] = DETAIL_CACHE
    return {
        "name": org.name,
        "slug": org.slug,
        "website": org.website,
        "open_roles": [_public_job(job, org) for job in jobs],
    }
