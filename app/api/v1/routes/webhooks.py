"""Clerk webhook receiver — keeps the local user/org mirror in sync.

Clerk signs with Svix headers. Verified here manually rather than pulling in the SDK:
signature is base64(HMAC-SHA256(f"{id}.{timestamp}.{body}", secret)).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Forbidden
from app.db.session import get_session
from app.models import Membership, Organization, User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

TOLERANCE_SECONDS = 300


def _verify(body: bytes, svix_id: str, svix_timestamp: str, svix_signature: str) -> None:
    secret = settings.clerk_webhook_secret
    if not secret:
        raise Forbidden("Webhook secret is not configured.")

    try:
        age = abs(time.time() - int(svix_timestamp))
    except ValueError as exc:
        raise Forbidden("Malformed webhook timestamp.") from exc
    if age > TOLERANCE_SECONDS:
        raise Forbidden("Webhook timestamp outside the tolerance window.")

    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    # Header may carry several space-separated "v1,<sig>" values.
    candidates = [part.split(",", 1)[-1] for part in svix_signature.split(" ") if part]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise Forbidden("Webhook signature mismatch.")


async def _upsert_user(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_id = str(data["id"])
    emails = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    email = next(
        (e["email_address"] for e in emails if e.get("id") == primary_id),
        emails[0]["email_address"] if emails else None,
    )
    if not email:
        return

    existing = (
        await session.execute(select(User).where(User.clerk_user_id == clerk_id))
    ).scalar_one_or_none()
    full_name = " ".join(
        part for part in (data.get("first_name"), data.get("last_name")) if part
    ) or None

    if existing:
        existing.email = email
        existing.full_name = full_name
    else:
        session.add(
            User(clerk_user_id=clerk_id, email=email, full_name=full_name, type="candidate")
        )


async def _upsert_org(session: AsyncSession, data: dict[str, Any]) -> None:
    clerk_id = str(data["id"])
    existing = (
        await session.execute(select(Organization).where(Organization.clerk_org_id == clerk_id))
    ).scalar_one_or_none()
    name = str(data.get("name") or "Untitled organization")
    slug = str(data.get("slug") or clerk_id.lower())

    if existing:
        existing.name = name
        existing.slug = slug
    else:
        session.add(
            Organization(
                clerk_org_id=clerk_id,
                name=name,
                slug=slug,
                monthly_token_budget=settings.default_org_monthly_token_budget,
            )
        )


async def _upsert_membership(session: AsyncSession, data: dict[str, Any]) -> None:
    org_clerk_id = str((data.get("organization") or {}).get("id", ""))
    user_clerk_id = str((data.get("public_user_data") or {}).get("user_id", ""))
    if not org_clerk_id or not user_clerk_id:
        return

    org = (
        await session.execute(select(Organization).where(Organization.clerk_org_id == org_clerk_id))
    ).scalar_one_or_none()
    user = (
        await session.execute(select(User).where(User.clerk_user_id == user_clerk_id))
    ).scalar_one_or_none()
    if not org or not user:
        return

    role = str(data.get("role") or "recruiter").removeprefix("org:")
    existing = (
        await session.execute(
            select(Membership).where(Membership.org_id == org.id, Membership.user_id == user.id)
        )
    ).scalar_one_or_none()

    if existing:
        existing.role = role
    else:
        session.add(Membership(org_id=org.id, user_id=user.id, role=role))
        user.type = "employer"


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT, summary="Clerk user/org sync")
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(alias="svix-id"),
    svix_timestamp: str = Header(alias="svix-timestamp"),
    svix_signature: str = Header(alias="svix-signature"),
    session: AsyncSession = Depends(get_session),
) -> None:
    body = await request.body()
    _verify(body, svix_id, svix_timestamp, svix_signature)

    payload: dict[str, Any] = await request.json()
    event = str(payload.get("type", ""))
    data: dict[str, Any] = payload.get("data") or {}

    if event in {"user.created", "user.updated"}:
        await _upsert_user(session, data)
    elif event in {"organization.created", "organization.updated"}:
        await _upsert_org(session, data)
    elif event in {"organizationMembership.created", "organizationMembership.updated"}:
        await _upsert_membership(session, data)
    # Deletions are intentionally not handled here: removing a user must go through the
    # account-deletion path, which anonymizes applications rather than cascading
    # (docs/02-data-model.md §9).
