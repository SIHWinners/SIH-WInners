"""Session tokens and role checks.

Tokens carry the Supabase claim shape so the same verification works for dev-issued
tokens and real Supabase Auth tokens (ADR-007)."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Request

from app.config import get_settings
from app.errors import ProblemError, forbidden

ALGORITHM = "HS256"


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: str
    partner_id: UUID | None = None
    csc_id: str | None = None
    lang: str = "en"

    @property
    def actor(self) -> str:
        return f"{self.role}:{self.user_id}"

    def claims(self) -> dict[str, Any]:
        return {"sub": str(self.user_id), "app_role": self.role,
                "partner_id": str(self.partner_id) if self.partner_id else None}


def issue_token(principal: Principal) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(UTC)
    ttl = s.jwt_ttl_minutes * 60
    payload = {
        "iss": "schememitra-dev" if s.auth_mode == "dev" else "supabase",
        "aud": "authenticated",
        "sub": str(principal.user_id),
        "role": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "app_metadata": {
            "app_role": principal.role,
            "partner_id": str(principal.partner_id) if principal.partner_id else None,
            "csc_id": principal.csc_id,
        },
        "user_metadata": {"lang": principal.lang},
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM), ttl


def decode_token(token: str) -> Principal:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=[ALGORITHM], audience="authenticated")
    except jwt.PyJWTError as err:
        raise ProblemError(401, "Invalid or expired session", "errors.unauthorized") from err
    meta = data.get("app_metadata") or {}
    partner = meta.get("partner_id")
    return Principal(
        user_id=UUID(data["sub"]),
        role=meta.get("app_role", "citizen"),
        partner_id=UUID(partner) if partner else None,
        csc_id=meta.get("csc_id"),
        lang=(data.get("user_metadata") or {}).get("lang", "en"),
    )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


async def optional_principal(request: Request) -> Principal | None:
    token = _bearer(request)
    return decode_token(token) if token else None


async def current_principal(request: Request) -> Principal:
    token = _bearer(request)
    if not token:
        raise ProblemError(401, "Sign-in required", "errors.unauthorized")
    return decode_token(token)


def require_roles(*roles: str) -> Callable[..., Coroutine[Any, Any, Principal]]:
    async def dep(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in roles:
            raise forbidden(f"requires one of {roles}")
        return principal

    return dep


def require_internal(request: Request) -> None:
    if request.headers.get("x-internal-secret") != get_settings().internal_shared_secret:
        raise forbidden("internal endpoint")
