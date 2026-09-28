"""Clerk JWT verification and the request-scoped identity dependencies.

Authorization is derived from the token only. Never trust a client-supplied org id.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from app.core.config import settings
from app.core.errors import Forbidden, NotFound

Role = Literal["candidate", "recruiter", "hiring_manager", "org_admin", "platform_admin"]
EMPLOYER_ROLES: frozenset[str] = frozenset({"recruiter", "hiring_manager", "org_admin"})

_jwk_client: PyJWKClient | None = None
_jwk_fetched_at: float = 0.0
_JWK_TTL = 3600.0


def _jwks() -> PyJWKClient:
    global _jwk_client, _jwk_fetched_at
    now = time.time()
    if _jwk_client is None or now - _jwk_fetched_at > _JWK_TTL:
        _jwk_client = PyJWKClient(f"{settings.clerk_issuer.rstrip('/')}/.well-known/jwks.json")
        _jwk_fetched_at = now
    return _jwk_client


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str           # Clerk user id (sub)
    email: str | None
    org_id: str | None     # Clerk org id, None for candidates
    role: Role

    @property
    def is_employer(self) -> bool:
        return self.role in EMPLOYER_ROLES

    def require_org(self) -> str:
        if not self.org_id:
            raise Forbidden("This endpoint requires an organization context.")
        return self.org_id


class Unauthenticated(Exception):
    pass


def _decode(token: str) -> dict[str, Any]:
    signing_key = _jwks().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=settings.clerk_issuer,
        audience=settings.clerk_audience or None,
        options={"verify_aud": bool(settings.clerk_audience)},
    )


# The single local identity used when DEV_AUTH is on. Deliberately obvious in logs and
# in the database, so nobody mistakes seeded demo activity for a real user.
DEV_PRINCIPAL = Principal(
    user_id="user_dev_local",
    email="dev@hirebridge.local",
    org_id="org_dev_local",
    role="org_admin",
)


async def current_principal(request: Request) -> Principal:
    if settings.dev_auth:
        # Settings refuses dev_auth outside ENVIRONMENT=local, so reaching here in a
        # deployed environment is impossible rather than merely discouraged.
        return DEV_PRINCIPAL

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise Forbidden("Missing bearer token.")
    try:
        claims = _decode(header.removeprefix("Bearer ").strip())
    except (jwt.PyJWTError, httpx.HTTPError) as exc:
        raise Forbidden("Invalid or expired token.") from exc

    return Principal(
        user_id=str(claims["sub"]),
        email=claims.get("email"),
        org_id=claims.get("org_id"),
        role=claims.get("org_role") or claims.get("role") or "candidate",
    )


CurrentPrincipal = Depends(current_principal)


def require_roles(*roles: Role) -> Any:
    async def _dep(principal: Principal = CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            # 404, not 403: a 403 would confirm the resource exists.
            raise NotFound("Not found.")
        return principal

    return Depends(_dep)
