from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.routes._deps import CurrentUser, Session, arq_pool
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models import Resume, ResumeVersion, StoredFile
from app.schemas.enums import ValidatorStatus
from app.schemas.resume import TailoredResume
from app.services.idempotency import IdempotencyKey, get_or_create_run
from app.services.resume_diff import compute_diff
from app.services.storage import get_storage
from app.workers.settings import QUEUE_GENERATE, QUEUE_PARSE

router = APIRouter(prefix="/resumes", tags=["resumes"])


class CreateResume(BaseModel):
    file_id: uuid.UUID
    label: str = "My CV"


class TailorRequest(BaseModel):
    job_id: uuid.UUID | None = None
    job_description_raw: str | None = None
    template: str = "modern"


def _accepted(run_id: uuid.UUID) -> dict[str, Any]:
    return {
        "run_id": str(run_id),
        "status": "queued",
        "poll": f"/v1/runs/{run_id}",
        "events": f"/v1/runs/{run_id}/events",
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_resume(
    body: CreateResume,
    user: CurrentUser,
    session: Session,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    stored = await session.get(StoredFile, body.file_id)
    if stored is None or stored.owner_user_id != user.id:
        raise NotFound("File not found.")
    if not stored.is_servable:
        raise Unprocessable("That file is still being checked. Try again in a moment.")

    resume = Resume(user_id=user.id, label=body.label, source_file_id=stored.id, is_base=True)
    session.add(resume)
    await session.flush()

    run, created = await get_or_create_run(
        session, agent="resume_parser", principal_user_id=str(user.clerk_user_id),
        idempotency_key=idempotency_key, user_id=user.id,
        subject_type="resume", subject_id=resume.id,
    )
    await session.commit()

    if created:
        pool = await arq_pool()
        await pool.enqueue_job("parse_resume", str(run.id), str(resume.id), _queue_name=QUEUE_PARSE)
    return {**_accepted(run.id), "resume_id": str(resume.id)}


@router.post("/{resume_id}/tailor", status_code=status.HTTP_202_ACCEPTED)
async def tailor(
    resume_id: uuid.UUID,
    body: TailorRequest,
    user: CurrentUser,
    session: Session,
    idempotency_key: IdempotencyKey = None,
) -> dict[str, Any]:
    """Accepts a raw JD as well as a job id, so the candidate tools work against jobs that
    are not on HireBridge — the cold-start hedge from the product brief."""
    if not body.job_id and not body.job_description_raw:
        raise Unprocessable("Provide either job_id or job_description_raw.")

    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise NotFound("Resume not found.")

    run, created = await get_or_create_run(
        session, agent="cv_tailor", principal_user_id=str(user.clerk_user_id),
        idempotency_key=idempotency_key, user_id=user.id,
        subject_type="resume", subject_id=resume.id,
    )
    await session.commit()

    if created:
        pool = await arq_pool()
        await pool.enqueue_job(
            "tailor_cv", str(run.id), str(resume.id),
            str(body.job_id) if body.job_id else None,
            body.job_description_raw,
            _queue_name=QUEUE_GENERATE,
        )
    return _accepted(run.id)


@router.get("/{resume_id}/versions")
async def list_versions(
    resume_id: uuid.UUID, user: CurrentUser, session: Session
) -> list[dict[str, Any]]:
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise NotFound("Resume not found.")

    rows = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.version.desc())
        )
    ).scalars().all()

    return [
        {
            "id": str(v.id), "version": v.version, "kind": v.kind,
            "validator_status": v.validator_status,
            "approved": v.approved_by_user_at is not None,
            "target_job_id": str(v.target_job_id) if v.target_job_id else None,
            "created_at": v.created_at,
        }
        for v in rows
    ]
