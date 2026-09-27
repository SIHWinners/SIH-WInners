"""Inbound SMS (claims C13, C14): an application, or a status lookup, from a phone with no
data connection. Parts are stored until the whole message has arrived, then decoded, and the
reply goes back over the same channel in the sender's language.

An SMS application creates a *draft* with the best-fitting scheme and nearest healthy lender
already chosen. It is never submitted automatically: papers and consent still have to come
from the app, a CSC or the lender's counter."""

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.crypto import keyed_hash, normalize_phone
from app.core.i18n import LOCALES, t
from app.core.ids import new_tracking_id, normalize_tracking_id
from app.db.base import utcnow
from app.db.models import Applicant, Application, SmsInboundPart, User
from app.modules.analytics import events as analytics
from app.modules.applications import service as applications
from app.modules.eligibility.schemas import ApplicantFacts
from app.modules.eligibility.service import evaluate
from app.modules.notify import codec
from app.modules.notify.sms import get_sms_provider, segments
from app.modules.routing.districts import BY_CODE, district_for_pincode
from app.modules.routing.service import nearby

PART_TTL = timedelta(hours=6)
REPLY_KEYS = {"apply": "sms.sms_draft_received", "not_found": "sms.not_found", "unknown": "sms.unknown_command"}


async def _reply(session: AsyncSession, phone: str, lang: str, key: str, **params: Any) -> dict[str, Any]:
    body = t(lang, key, **params)
    result = await get_sms_provider().send(phone, body)
    from app.db.models import Notification

    session.add(Notification(channel="sms", to_hash=keyed_hash(phone, "phone"), to_masked=f"******{phone[-4:]}",
                             template_id=key, lang=lang, payload=params, body=body, segments=segments(body),
                             status=result.status, provider=result.provider, provider_msg_id=result.provider_msg_id))
    return {"reply_key": key, "body": body, "segments": segments(body)}


async def _store_part(session: AsyncSession, sender_hash: str, part: codec.Part) -> list[str]:
    await session.execute(delete(SmsInboundPart).where(SmsInboundPart.received_at < utcnow() - PART_TTL))
    existing = (await session.execute(
        select(SmsInboundPart).where(SmsInboundPart.sender_hash == sender_hash, SmsInboundPart.message_ref == part.ref)
    )).scalars().all()
    if not any(p.part_no == part.part for p in existing):
        session.add(SmsInboundPart(sender_hash=sender_hash, message_ref=part.ref, part_no=part.part,
                                   part_total=part.total,
                                   body=f"SM1*{part.ref}{part.part}{part.total}*{part.body}*{part.crc}"))
        await session.flush()
    rows = (await session.execute(
        select(SmsInboundPart).where(SmsInboundPart.sender_hash == sender_hash, SmsInboundPart.message_ref == part.ref)
        .order_by(SmsInboundPart.part_no)
    )).scalars().all()
    return [row.body for row in rows]


async def _clear_parts(session: AsyncSession, sender_hash: str, ref: str) -> None:
    await session.execute(delete(SmsInboundPart).where(SmsInboundPart.sender_hash == sender_hash,
                                                        SmsInboundPart.message_ref == ref))


def _facts_from_sms(decoded: dict[str, Any]) -> tuple[ApplicantFacts, str | None, str]:
    """SMS carries rupees and short codes; the rules work in paise."""
    lang = decoded.get("lang") if decoded.get("lang") in LOCALES else None
    district_code = decoded.get("district_code")
    if not district_code and decoded.get("pincode"):
        district = district_for_pincode(str(decoded["pincode"]))
        district_code = district.code if district else None
    district = BY_CODE.get(district_code or "")
    facts = ApplicantFacts(
        age=decoded.get("age"), gender=decoded.get("gender"), social_category=decoded.get("social_category"),
        has_disability=decoded.get("has_disability", False), state_code=decoded.get("state_code") or (district.state_code if district else None),
        district_code=district_code, pincode=decoded.get("pincode"),
        annual_family_income_paise=int(decoded["annual_family_income_rupees"]) * 100 if decoded.get("annual_family_income_rupees") is not None else None,
        education_level=decoded.get("education_level"), business_type=decoded.get("business_type"),
        project_cost_paise=int(decoded["project_cost_rupees"]) * 100 if decoded.get("project_cost_rupees") is not None else None,
        loan_needed_paise=int(decoded["loan_needed_rupees"]) * 100 if decoded.get("loan_needed_rupees") is not None else None,
        shg_member=decoded.get("shg_member"), existing_loans=decoded.get("existing_loans"),
        lat=district.lat if district else None, lng=district.lng if district else None,
    )
    return facts, decoded.get("full_name"), lang or "hi"


async def _create_draft_from_sms(session: AsyncSession, phone: str, decoded: dict[str, Any]) -> tuple[str | None, str]:
    facts, full_name, lang = _facts_from_sms(decoded)
    result = await evaluate(session, facts)
    if not result["eligible"]:
        return None, lang
    code = result["eligible"][0]
    scheme = next(r for r in result["results"] if r["code"] == code)
    partner_id = None
    if facts.lat is not None and facts.lng is not None:
        found = await nearby(session, lat=facts.lat, lng=facts.lng, scheme=code, category=facts.social_category,
                             radius_km=60.0, loan_paise=facts.loan_needed_paise, limit=1)
        partner_id = found["partners"][0]["id"] if found["partners"] else None
    if partner_id is None:
        return None, lang

    user = (await session.execute(select(User).where(User.phone_hash == keyed_hash(normalize_phone(phone), "phone")))).scalar_one_or_none()
    applicant = Applicant(user_id=user.id if user else None, full_name_enc=full_name, phone_enc=phone,
                          gender=facts.gender, social_category=facts.social_category,
                          disability_flag=bool(facts.has_disability), state_code=facts.state_code,
                          district_code=facts.district_code, pincode=facts.pincode, lat=facts.lat, lng=facts.lng,
                          annual_family_income_paise=facts.annual_family_income_paise,
                          education_level=facts.education_level,
                          profile={"age": facts.age, "business_type": facts.business_type,
                                   "project_cost_paise": facts.project_cost_paise,
                                   "loan_needed_paise": facts.loan_needed_paise,
                                   "existing_loans": facts.existing_loans, "shg_member": facts.shg_member,
                                   "course_admitted": facts.course_admitted})
    session.add(applicant)
    await session.flush()

    offer = scheme["offer"]
    principal = offer["suggested_principal_paise"] or min(facts.loan_needed_paise or offer["max_loan_paise"], offer["max_loan_paise"])
    app = Application(
        tracking_id=new_tracking_id(facts.state_code or "IN"), applicant_id=applicant.id, partner_id=UUID(partner_id),
        status="draft", submitted_via="sms", lang=lang,
        status_history=[{"status": "draft", "at": utcnow().isoformat(timespec="seconds"), "by": "sms"}],
        requested_amount_paise=principal, project_cost_paise=facts.project_cost_paise,
        tenure_months=offer["default_tenure_months"], moratorium_months=offer["moratorium_default_months"],
        interest_rate_bps=offer["rate_bps"],
        eligibility_trace={"scheme_code": code, "status": scheme["status"], "version": scheme["version"]},
        finance_summary={"plan": {"principal_paise": principal, "rate_bps": offer["rate_bps"],
                                  "tenure_months": offer["default_tenure_months"],
                                  "moratorium_months": offer["moratorium_default_months"],
                                  "treatment": offer["moratorium_treatment"], "frequency": offer["repayment_frequency"]}},
    )
    session.add(app)
    await session.flush()
    await audit.record(session, actor=f"sms:******{phone[-4:]}", actor_role="citizen", action="application.created",
                       entity=f"application:{app.tracking_id}", diff={"via": "sms", "scheme": code})
    await analytics.record(session, "application_created", step="send_track", lang=lang, facts=facts.facts(),
                           scheme_code=code)
    return app.tracking_id, lang


async def handle(session: AsyncSession, sender: str, text: str, provider: str) -> dict[str, Any]:
    """One inbound message. Returns what was understood and the reply that was sent."""
    phone = normalize_phone(sender)
    sender_hash = keyed_hash(phone, "phone")
    lang = "hi"

    part = codec.parse_part(text)
    texts = [text]
    if part is not None:
        texts = await _store_part(session, sender_hash, part)
    decoded = codec.decode(texts)

    if decoded.kind == "partial":
        return {"understood": "partial", "ref": decoded.ref, "received": decoded.received, "expected": decoded.parts}
    if decoded.kind == "status":
        try:
            tracking_id = normalize_tracking_id(decoded.tracking_id or "")
            track = await applications.track(session, tracking_id)
        except Exception:  # noqa: BLE001 - any lookup failure is "no such application" to the sender
            return {"understood": "status", "found": False,
                    **await _reply(session, phone, lang, "sms.not_found", tid=decoded.tracking_id or "")}
        lang = track.get("lang") or lang
        reply = await _reply(session, phone, lang, "sms.status", tid=tracking_id,
                             status=t(lang, f"track.status.{track['status']}"), next=t(lang, track["next_step_key"]))
        return {"understood": "status", "found": True, "tracking_id": tracking_id, **reply}
    if decoded.kind == "apply":
        if part:
            await _clear_parts(session, sender_hash, part.ref)
        created_tid, lang = await _create_draft_from_sms(session, phone, decoded.facts)
        if created_tid is None:
            return {"understood": "apply", "created": False,
                    **await _reply(session, phone, lang, "sms.unknown_command")}
        return {"understood": "apply", "created": True, "tracking_id": created_tid,
                **await _reply(session, phone, lang, "sms.sms_draft_received", tid=created_tid)}
    return {"understood": decoded.kind, "reason": decoded.reason,
            **await _reply(session, phone, lang, "sms.unknown_command")}


async def ivr_menu(session: AsyncSession, tracking_id: str | None, lang: str) -> dict[str, Any]:
    """IVR stub (spec §9.8): what the voice line would read out. Real telephony is a pilot task —
    this returns the exact prompts so the flow can be demonstrated and recorded."""
    lang = lang if lang in LOCALES else "hi"
    if not tracking_id:
        return {"say": t(lang, "track.enter_id"), "expect": "tracking_id", "lang": lang}
    try:
        track = await applications.track(session, normalize_tracking_id(tracking_id))
    except Exception:  # noqa: BLE001
        return {"say": t(lang, "sms.not_found", tid=tracking_id), "expect": "tracking_id", "lang": lang}
    say = " ".join([
        t(lang, "sms.status", tid=track["tracking_id"], status=t(lang, f"track.status.{track['status']}"),
          next=t(lang, track["next_step_key"])),
        t(lang, "common.free_service"),
    ])
    return {"say": say, "expect": "end", "lang": lang, "status": track["status"],
            "partner": track.get("partner_name")}
