"""Phone OTP sign-in. In dev/demo the OTP is logged to the console (and returned in the
response when DEMO_MODE is on, so judges don't need a phone). Brute force is capped by
per-challenge attempts plus a lockout window per phone."""

import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import audit
from app.core.crypto import keyed_hash, normalize_phone, phone_hash
from app.core.security import Principal, issue_token
from app.db.base import utcnow
from app.db.models import ROLES, OtpChallenge, User
from app.errors import ProblemError
from app.logging import get_logger

log = get_logger("auth")


def _code_hash(phone_h: str, code: str) -> str:
    return keyed_hash(f"{phone_h}:{code}", "otp")


async def _locked_until(session: AsyncSession, phone_h: str) -> OtpChallenge | None:
    now = utcnow()
    row = (
        await session.execute(
            select(OtpChallenge)
            .where(OtpChallenge.phone_hash == phone_h, OtpChallenge.locked_until.is_not(None))
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row and row.locked_until and row.locked_until > now:
        return row
    return None


async def request_otp(session: AsyncSession, phone: str) -> dict[str, object]:
    s = get_settings()
    digits = normalize_phone(phone)
    if len(digits) != 10 or digits[0] not in "6789":
        raise ProblemError(422, "Invalid mobile number", "errors.invalid_phone")
    ph = phone_hash(digits)
    if await _locked_until(session, ph):
        raise ProblemError(429, "Too many attempts", "errors.otp_locked")
    code = f"{secrets.randbelow(10**6):06d}"
    session.add(OtpChallenge(phone_hash=ph, code_hash=_code_hash(ph, code),
                             expires_at=utcnow() + timedelta(seconds=s.otp_ttl_seconds)))
    await session.commit()
    # Console delivery in dev. Only the last 2 digits of the phone are shown.
    log.info("DEV OTP for ******%s is %s (SANDBOX SMS)", digits[-2:], code)
    body: dict[str, object] = {"sent": True, "ttl_seconds": s.otp_ttl_seconds, "channel": "console"}
    if s.demo_mode and s.env != "prod":
        body["dev_otp"] = code
    return body


async def verify_otp(session: AsyncSession, phone: str, code: str, lang: str = "en") -> dict[str, object]:
    s = get_settings()
    ph = phone_hash(phone)
    if await _locked_until(session, ph):
        raise ProblemError(429, "Too many attempts", "errors.otp_locked")
    challenge = (
        await session.execute(
            select(OtpChallenge)
            .where(OtpChallenge.phone_hash == ph, OtpChallenge.consumed.is_(False))
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if challenge is None or challenge.expires_at < utcnow():
        raise ProblemError(401, "OTP expired", "errors.otp_expired")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _code_hash(ph, code.strip())):
        if challenge.attempts >= s.otp_max_attempts:
            challenge.locked_until = utcnow() + timedelta(minutes=s.otp_lockout_minutes)
            challenge.consumed = True
        await session.commit()
        raise ProblemError(401, "Wrong OTP", "errors.otp_wrong",
                           extra={"attempts_left": max(0, s.otp_max_attempts - challenge.attempts)})
    challenge.consumed = True

    user = (await session.execute(select(User).where(User.phone_hash == ph))).scalar_one_or_none()
    if user is None:
        # First sign-in creates a citizen. Officer/operator/admin accounts are provisioned.
        user = User(role="citizen", phone_hash=ph, phone_enc=normalize_phone(phone), preferred_lang=lang)
        session.add(user)
        await session.flush()
        await audit.record(session, actor=f"citizen:{user.id}", actor_role="citizen",
                           action="user.created", entity=f"user:{user.id}")
    assert user.role in ROLES
    principal = Principal(user_id=user.id, role=user.role, partner_id=user.partner_id, csc_id=user.csc_id,
                          lang=user.preferred_lang)
    token, ttl = issue_token(principal)
    await audit.record(session, actor=principal.actor, actor_role=user.role, action="auth.login",
                       entity=f"user:{user.id}")
    await session.commit()
    return {
        "access_token": token, "token_type": "bearer", "expires_in": ttl,
        "user": {"id": str(user.id), "role": user.role, "partner_id": str(user.partner_id) if user.partner_id
                 else None, "csc_id": user.csc_id, "display_name": user.display_name,
                 "preferred_lang": user.preferred_lang},
    }
