from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.v1.routes._deps import CurrentUser, Session
from app.core.errors import NotFound, Unprocessable
from app.models import Resume, ResumeVersion
from app.schemas.enums import ValidatorStatus
from app.schemas.resume import TailoredResume
from app.services.resume_diff import compute_diff
from app.services.storage import get_storage

router = APIRouter(prefix="/resume-versions", tags=["resumes"])


async def _owned(session: Session, version_id: uuid.UUID, user: CurrentUser) -> ResumeVersion:  # type: ignore[valid-type]
    version = await session.get(ResumeVersion, version_id)
    if version is None:
        raise NotFound("Version not found.")
    resume = await session.get(Resume, version.resume_id)
    if resume is None or resume.user_id != user.id:
        raise NotFound("Version not found.")
    return version


@router.get("/{version_id}/diff")
async def diff(version_id: uuid.UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Backs the screen the candidate product rests on.

    The summary's `added: 0` is the visible proof that nothing was invented.
    """
    version = await _owned(session, version_id, user)
    base = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == version.resume_id, ResumeVersion.kind == "base")
            .order_by(ResumeVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if base is None:
        raise Unprocessable("No base CV to compare against.")

    result = compute_diff(
        TailoredResume.model_validate(base.content),
        TailoredResume.model_validate(version.content),
    )
    return {
        **result.as_dict(),
        "validator_status": version.validator_status,
        "validator_findings": version.validator_findings or [],
    }


@router.post("/{version_id}/approve")
async def approve(version_id: uuid.UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Explicit human approval. Nothing generated reaches an employer without it."""
    version = await _owned(session, version_id, user)
    if version.validator_status == ValidatorStatus.FAILED.value:
        raise Unprocessable(
            "This version could not be verified against your profile and cannot be sent. "
            "Try tailoring again, or apply with your base CV."
        )
    version.approved_by_user_at = datetime.now(UTC)
    return {"id": str(version.id), "approved_at": version.approved_by_user_at}


@router.get("/{version_id}/pdf", status_code=status.HTTP_302_FOUND)
async def pdf(version_id: uuid.UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    version = await _owned(session, version_id, user)
    if version.pdf_file_id is None:
        raise Unprocessable("The PDF for this version has not been rendered yet.")
    if version.approved_by_user_at is None:
        raise Unprocessable("Approve this version before downloading it.")
    from app.models import StoredFile

    stored = await session.get(StoredFile, version.pdf_file_id)
    if stored is None:
        raise NotFound("PDF not found.")
    return {"url": await get_storage().presign_download(stored.storage_key)}
