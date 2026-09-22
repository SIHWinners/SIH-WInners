"""Status notifications: SMS in the applicant's language, with in-app push as the fallback when
the SMS provider is down (spec §13), and a WebSocket event so open screens update instantly."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.crypto import keyed_hash, normalize_phone
from app.core.i18n import t
from app.core.resilience import guarded
from app.db.models import Applicant, Application, Notification, Partner
from app.logging import get_logger
from app.modules.applications.status import SMS_TEMPLATE
from app.modules.notify.sms import SendResult, get_sms_provider, segments

log = get_logger("notify")


def _short_partner(name: str | None) -> str:
    return (name or "").replace(" (demo)", "")[:40]


def compose_status_sms(app: Application, partner: Partner | None) -> tuple[str, str, dict[str, Any]]:
    lang = app.lang
    key = SMS_TEMPLATE.get(app.status, "sms.status")
    params: dict[str, Any] = {
        "tid": app.tracking_id, "partner": _short_partner(partner.name if partner else ""),
        "status": t(lang, f"track.status.{app.status}"), "next": t(lang, f"track.next.{app.status}"),
        "docs": ", ".join(t(lang, f"docs.type.{d}") for d in app.requested_documents or []),
        "reason": t(lang, f"reject_reason.{app.rejection_reason_code or 'other'}"),
    }
    return key, t(lang, key, **params), params


async def notify_status(session: AsyncSession, app: Application, applicant: Applicant, partner: Partner | None) -> None:
    key, body, params = compose_status_sms(app, partner)
    phone = normalize_phone(applicant.phone_enc or "")
    push_payload = {"tracking_id": app.tracking_id, "status": app.status, "template": key}

    async def send_sms() -> SendResult:
        if len(phone) != 10:
            raise ValueError("no phone on file")
        return await get_sms_provider().send(phone, body)

    async def push_only() -> SendResult:
        return SendResult("push", None, "fallback_push", True)

    result, path = await guarded("sms", send_sms, push_only, attempts=2)
    if path == "primary":
        session.add(Notification(application_id=app.id, channel="sms", to_hash=keyed_hash(phone, "phone"),
                                 to_masked=f"******{phone[-4:]}", template_id=key, lang=app.lang, payload=params, body=body,
                                 segments=segments(body), status=result.status, provider=result.provider,
                                 provider_msg_id=result.provider_msg_id))
    session.add(Notification(application_id=app.id, channel="push", template_id=key, lang=app.lang, payload=push_payload,
                             body=body, status="sent", provider="in_app"))
    events.publish(f"track:{app.tracking_id}", "status", push_payload, session)
    if applicant.user_id:
        events.publish(f"user:{applicant.user_id}", "status", push_payload, session)
    if app.partner_id:
        events.publish(f"partner:{app.partner_id}", "application", push_payload, session)
