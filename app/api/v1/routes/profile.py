"""Candidate profile and the facts behind every generated CV line."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.routes._deps import CurrentUser, Session
from app.core.errors import NotFound
from app.models import CandidateProfile, FactKind, FactSource, ProfileFact
from app.schemas.profile import FactKindLiteral

router = APIRouter(prefix="/me/profile", tags=["profile"])

LOW_CONFIDENCE = 0.7


class ProfilePatch(BaseModel):
    headline: str | None = Field(default=None, max_length=200)
    summary: str | None = None
    location_city: str | None = Field(default=None, max_length=120)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    open_to_work: bool | None = None
    preferred_roles: list[str] | None = None


class FactIn(BaseModel):
    kind: FactKindLiteral
    payload: dict[str, Any]
    position: int = 0


class FactPatch(BaseModel):
    payload: dict[str, Any] | None = None
    position: int | None = None


async def _profile(session: Session, user_id: uuid.UUID) -> CandidateProfile:  # type: ignore[valid-type]
    profile = (
        await session.execute(
            select(CandidateProfile).where(CandidateProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = CandidateProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


def _fact_out(fact: ProfileFact) -> dict[str, Any]:
    return {
        "id": str(fact.id),
        "kind": fact.kind,
        "payload": fact.payload,
        "source": fact.source,
        "confidence": float(fact.confidence),
        "verified_by_user": fact.verified_by_user,
        "needs_review": fact.needs_review,
        "start_date": fact.start_date,
        "end_date": fact.end_date,
        "position": fact.position,
    }


@router.get("")
async def get_profile(user: CurrentUser, session: Session) -> dict[str, Any]:
    profile = await _profile(session, user.id)
    return {
        "id": str(profile.id),
        "headline": profile.headline,
        "summary": profile.summary,
        "location_city": profile.location_city,
        "years_experience": float(profile.years_experience) if profile.years_experience else None,
        "open_to_work": profile.open_to_work,
        "preferred_roles": profile.preferred_roles or [],
        "completeness_score": profile.completeness_score,
    }


@router.patch("")
async def patch_profile(
    body: ProfilePatch, user: CurrentUser, session: Session
) -> dict[str, Any]:
    profile = await _profile(session, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    return {"id": str(profile.id)}


@router.get("/facts")
async def list_facts(
    user: CurrentUser, session: Session, kind: FactKindLiteral | None = None
) -> list[dict[str, Any]]:
    profile = await _profile(session, user.id)
    stmt = (
        select(ProfileFact)
        .where(ProfileFact.profile_id == profile.id)
        .order_by(ProfileFact.position)
    )
    if kind:
        stmt = stmt.where(ProfileFact.kind == kind)
    return [_fact_out(f) for f in (await session.execute(stmt)).scalars().all()]


@router.post("/facts", status_code=status.HTTP_201_CREATED)
async def create_fact(body: FactIn, user: CurrentUser, session: Session) -> dict[str, Any]:
    profile = await _profile(session, user.id)
    fact = ProfileFact(
        profile_id=profile.id,
        kind=body.kind,
        payload=body.payload,
        position=body.position,
        # Entered by hand, so it is certain and needs no review.
        source=FactSource.USER_ENTERED.value,
        confidence=1.0,
        verified_by_user=True,
    )
    session.add(fact)
    await session.flush()
    return _fact_out(fact)


async def _owned_fact(session: Session, fact_id: uuid.UUID, user_id: uuid.UUID) -> ProfileFact:  # type: ignore[valid-type]
    profile = await _profile(session, user_id)
    fact = await session.get(ProfileFact, fact_id)
    if fact is None or fact.profile_id != profile.id:
        raise NotFound("Fact not found.")
    return fact


@router.patch("/facts/{fact_id}")
async def patch_fact(
    fact_id: uuid.UUID, body: FactPatch, user: CurrentUser, session: Session
) -> dict[str, Any]:
    fact = await _owned_fact(session, fact_id, user.id)
    if body.payload is not None:
        fact.payload = body.payload
        # An edited fact is the user's own statement now, whatever the parser read.
        fact.source = FactSource.USER_EDITED.value
        fact.confidence = 1.0
        fact.verified_by_user = True
    if body.position is not None:
        fact.position = body.position
    return _fact_out(fact)


@router.post("/facts/{fact_id}/verify")
async def verify_fact(
    fact_id: uuid.UUID, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Confirming a parsed fact without editing it. The onboarding review step calls this."""
    fact = await _owned_fact(session, fact_id, user.id)
    fact.verified_by_user = True
    return _fact_out(fact)


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(fact_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    fact = await _owned_fact(session, fact_id, user.id)
    await session.delete(fact)


@router.get("/completeness")
async def completeness(user: CurrentUser, session: Session) -> dict[str, Any]:
    """Names what is missing.

    A bare percentage tells someone they are incomplete without telling them what to do
    about it (docs/02-routes-and-screens.md).
    """
    profile = await _profile(session, user.id)
    facts = (
        await session.execute(
            select(ProfileFact).where(ProfileFact.profile_id == profile.id)
        )
    ).scalars().all()

    kinds = {f.kind for f in facts}
    bullets = sum(len((f.payload or {}).get("bullets", [])) for f in facts)
    unverified = [f for f in facts if f.needs_review]

    missing: list[str] = []
    if FactKind.EXPERIENCE.value not in kinds:
        missing.append("Add at least one role you have held.")
    if FactKind.EDUCATION.value not in kinds:
        missing.append("Add your education.")
    if FactKind.SKILL.value not in kinds:
        missing.append("List the tools and languages you work with.")
    if FactKind.PROJECT.value not in kinds:
        missing.append("Add a project — it gives the tailoring more to draw on.")
    if bullets < 4:
        missing.append("Describe what you did in each role; a few bullets each is plenty.")
    if unverified:
        missing.append(
            f"Confirm {len(unverified)} detail{'s' if len(unverified) > 1 else ''} "
            "we were unsure about when reading your CV."
        )

    return {
        "score": profile.completeness_score,
        "missing": missing,
        "needs_review": [str(f.id) for f in unverified],
    }
