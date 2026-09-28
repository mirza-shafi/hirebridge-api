from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.routes._deps import CurrentUser, Session
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models import (
    Application,
    ApplicationEvent,
    ApplicationStage,
    Job,
    JobStatus,
    ResumeVersion,
)
from app.schemas.enums import can_transition

router = APIRouter(prefix="/applications", tags=["applications"])


class CreateApplication(BaseModel):
    job_id: uuid.UUID
    resume_version_id: uuid.UUID
    cover_note: str | None = None


class ChangeStage(BaseModel):
    stage: ApplicationStage
    note: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def apply(
    body: CreateApplication, user: CurrentUser, session: Session
) -> dict[str, Any]:
    job = await session.get(Job, body.job_id)
    if job is None or job.status != JobStatus.PUBLISHED.value:
        raise NotFound("Job not found.")

    version = await session.get(ResumeVersion, body.resume_version_id)
    if version is None:
        raise NotFound("Resume version not found.")
    if not version.is_sendable:
        # Enforced at the data layer too; this is the readable error.
        raise Unprocessable(
            "Approve this CV version before sending it. If it failed verification, "
            "tailor it again or apply with your base CV."
        )

    existing = (
        await session.execute(
            select(Application).where(
                Application.job_id == job.id, Application.candidate_user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise Conflict("You have already applied to this role.")

    application = Application(
        job_id=job.id, candidate_user_id=user.id, resume_version_id=version.id,
        cover_note=body.cover_note, stage=ApplicationStage.NEW.value,
        profile_snapshot={"resume_version": version.version, "content": version.content},
    )
    session.add(application)
    await session.flush()
    session.add(
        ApplicationEvent(
            application_id=application.id, actor_user_id=user.id,
            actor_type="user", event="created",
        )
    )
    return {"id": str(application.id), "stage": application.stage}


@router.patch("/{application_id}/stage")
async def change_stage(
    application_id: uuid.UUID, body: ChangeStage, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """A decision about a person. Named actor, validated transition, audit row — always."""
    application = await session.get(Application, application_id)
    if application is None:
        raise NotFound("Application not found.")

    current = ApplicationStage(application.stage)
    if current == body.stage:
        return {"id": str(application.id), "stage": application.stage}

    if not can_transition(current, body.stage):
        raise Unprocessable(
            f"An application cannot move from {current.value} to {body.stage.value}."
        )

    application.stage = body.stage.value
    application.stage_changed_at = datetime.now(UTC)
    application.stage_changed_by = user.id
    session.add(
        ApplicationEvent(
            application_id=application.id, actor_user_id=user.id, actor_type="user",
            event="stage_changed",
            payload={"from": current.value, "to": body.stage.value, "note": body.note},
        )
    )
    return {"id": str(application.id), "stage": application.stage}


@router.get("/{application_id}/events")
async def events(
    application_id: uuid.UUID, user: CurrentUser, session: Session
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.created_at)
        )
    ).scalars().all()
    return [
        {
            "event": e.event, "actor_type": e.actor_type,
            "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
            "payload": e.payload, "at": e.created_at,
        }
        for e in rows
    ]
