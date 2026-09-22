"""Partner portal: queue, QR scan with signature + integrity check, file review, and decisions.

Only a partner officer of the lender the file was sent to can move it to sanctioned,
rejected or disbursed (status.LENDER_DECISIONS, claim C21)."""

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.core.storage import get_storage
from app.db.base import utcnow
from app.db.models import Applicant, Application, AuditLog, Consent, Partner
from app.errors import ProblemError, forbidden
from app.modules.applications import qr, status
from app.modules.applications import service as apps
from app.modules.applications.access import load_for
from app.modules.documents.service import document_out
from app.modules.finance.calc import LoanInput, build_schedule
from app.modules.partner.schemas import ACTION_TARGET, DecisionIn

GROUPS = {"new": ("submitted", "resubmitted"), "in_review": ("received_by_partner", "under_review", "documents_requested"),
          "decided": ("sanctioned", "rejected", "disbursed")}
OVERDUE_HOURS = 72


def _scope(query: Any, principal: Principal) -> Any:
    query = query.where(Application.deleted_at.is_(None), Application.status.notin_(("draft", "ready")))
    if principal.role == "partner_officer":
        if principal.partner_id is None:
            raise forbidden("officer is not linked to a lender")
        query = query.where(Application.partner_id == principal.partner_id)
    return query


async def queue(session: AsyncSession, principal: Principal, group: str, q: str | None) -> dict[str, Any]:
    rows = (await session.execute(_scope(select(Application), principal).order_by(Application.submitted_at.desc()).limit(500))).scalars().all()
    ruleset = await apps.get_ruleset(session)
    now = utcnow()
    counts = {name: 0 for name in GROUPS} | {"all": 0}
    items = []
    for app in rows:
        counts["all"] += 1
        for name, statuses in GROUPS.items():
            if app.status in statuses:
                counts[name] += 1
        if group != "all" and app.status not in GROUPS.get(group, ()):
            continue
        applicant = await session.get(Applicant, app.applicant_id)
        assert applicant is not None
        name = applicant.full_name_enc or "—"
        if q and q.lower() not in f"{name} {app.tracking_id}".lower():
            continue
        code = (app.eligibility_trace or {}).get("scheme_code")
        scheme = ruleset.schemes.get(code) if code else None
        age = (now - app.submitted_at).total_seconds() / 3600 if app.submitted_at else None
        items.append({
            "id": str(app.id), "tracking_id": app.tracking_id, "status": app.status, "applicant_name": name,
            "district": apps.district_label(applicant.district_code), "scheme_code": code,
            "scheme_name": scheme.doc["name"]["en"] if scheme else code,
            "amount_paise": (app.finance_summary or {}).get("plan", {}).get("principal_paise"),
            "submitted_at": app.submitted_at.isoformat(timespec="minutes") if app.submitted_at else None,
            "age_hours": round(age, 1) if age is not None else None, "readiness_score": app.completeness_score,
            "name_match_min": None, "submitted_via": app.submitted_via, "lang": app.lang,
            "overdue": bool(age and age > OVERDUE_HOURS and app.status in GROUPS["new"]),
        })
    partner = await session.get(Partner, principal.partner_id) if principal.partner_id else None
    return {"items": items, "counts": counts, "partner_name": partner.name if partner else None}


async def scan(session: AsyncSession, principal: Principal, jws: str) -> dict[str, Any]:
    """Verify the Ed25519 JWS from the citizen's QR, then open the file. A lender can only open
    files addressed to it; the QR itself carries no personal data."""
    claims = qr.verify_qr(jws)
    app = (await session.execute(select(Application).where(Application.tracking_id == claims["tid"]))).scalar_one_or_none()
    if app is None or app.deleted_at is not None:
        raise ProblemError(404, "No application for this QR", "errors.not_found")
    if principal.role == "partner_officer" and str(principal.partner_id) != claims["pid"]:
        raise ProblemError(403, "This file was sent to another lender", "officer.scan_other_lender")
    app, applicant = await load_for(session, app.id, principal)
    docs = await apps.documents_of(session, app)
    unchanged = apps.content_hash(app, applicant, docs)[:32] == claims["h"]
    received_now = False
    if app.status == "submitted" and principal.role == "partner_officer":
        await apps.transition(session, principal, app, applicant, "received_by_partner", note="received by QR scan")
        received_now = True
    return {"application_id": str(app.id), "tracking_id": app.tracking_id, "status": app.status, "signature_valid": True,
            "file_unchanged": unchanged, "issued_at": utcnow().fromtimestamp(claims["iat"]).isoformat(timespec="minutes"),
            "received_now": received_now}


def allowed_actions(app: Application, principal: Principal) -> list[str]:
    return [action for action, target in ACTION_TARGET.items() if status.can_transition(app.status, target, principal.role)
            and (principal.role != "admin" or target not in status.LENDER_DECISIONS)]


async def review(session: AsyncSession, principal: Principal, application_id: UUID) -> dict[str, Any]:
    from app.modules.applications.router import application_out

    app, applicant = await load_for(session, application_id, principal)
    view = await apps.loan_file_view(session, app, applicant)
    ready = view["readiness"]
    docs = await apps.documents_of(session, app)
    documents = []
    for doc in docs.values():
        out = document_out(doc)
        documents.append({**{k: out[k] for k in ("document_id", "type", "source", "status", "verified", "confidence", "sandbox",
                                                 "fields", "issues")},
                          "has_image": bool(doc.storage_key), "name_match": ready.get("name_matches", {}).get(doc.type)})
    consent = await session.get(Consent, applicant.consent_id) if applicant.consent_id else None
    trail = (await session.execute(select(AuditLog).where(AuditLog.entity == f"application:{app.tracking_id}")
                                   .order_by(AuditLog.seq))).scalars().all()
    unchanged = app.content_hash is not None and apps.content_hash(app, applicant, docs) == app.content_hash
    letter_key = f"applications/{app.id}/sanction-letter.pdf"
    return {
        "application": await application_out(session, app, applicant),
        "applicant": {**view["applicant"], "father_name": applicant.father_name_enc, "district_code": applicant.district_code,
                      "business_type": (applicant.profile or {}).get("business_type")},
        "scheme": {k: view["scheme"][k] for k in ("name_en", "name_local", "apex_corp", "version", "trace", "source_url",
                                                   "needs_verification")} | {"code": app.eligibility_trace.get("scheme_code")},
        "finance": {"plan": view["plan"], "split": view["split"], **{k: v for k, v in (app.finance_summary or {}).items()
                                                                     if k in ("sanction",)}},
        "documents": documents,
        "readiness": ready,
        "consent": {"method": consent.method, "language": consent.language, "text_version": consent.text_version,
                    "granted_at": consent.granted_at.isoformat(timespec="minutes"), "evidence": consent.evidence} if consent else None,
        "audit": [{"at": a.at.isoformat(timespec="seconds"), "actor_role": a.actor_role, "action": a.action, "diff": a.diff,
                   "hash": a.hash[:12]} for a in trail],
        "allowed_actions": allowed_actions(app, principal),
        "reject_reasons": list(status.REJECT_REASONS),
        "integrity": {"content_hash": (app.content_hash or "")[:16], "unchanged_since_submit": unchanged},
        "sanction_letter_url": f"/api/v1/applications/{app.id}/sanction-letter.pdf" if await get_storage().exists(letter_key) else None,
    }


def _terms(app: Application, body: DecisionIn) -> dict[str, Any]:
    plan = (app.finance_summary or {}).get("plan", {})
    given = body.sanction
    loan = LoanInput(
        principal_paise=given.amount_paise if given else int(plan["principal_paise"]),
        rate_bps=given.rate_bps if given else int(plan["rate_bps"]),
        tenure_months=given.tenure_months if given else int(plan["tenure_months"]),
        moratorium_months=given.moratorium_months if given else int(plan.get("moratorium_months", 0)),
        treatment=plan.get("treatment", "interest_capitalised"), frequency=plan.get("frequency", "monthly"),
    )
    schedule = build_schedule(loan)
    return {"amount_paise": loan.principal_paise, "rate_bps": loan.rate_bps, "tenure_months": loan.tenure_months,
            "moratorium_months": loan.moratorium_months, "frequency": loan.frequency, "emi_paise": schedule.instalment_paise,
            "total_payable_paise": schedule.total_payable_paise}


async def decide(session: AsyncSession, principal: Principal, application_id: UUID, body: DecisionIn) -> Application:
    app, applicant = await load_for(session, application_id, principal)
    target = ACTION_TARGET[body.action]
    if target in status.LENDER_DECISIONS and principal.role != "partner_officer":
        raise ProblemError(403, "Only the lender can make this decision", "officer.lender_only")
    if principal.role == "partner_officer" and app.partner_id != principal.partner_id:
        raise ProblemError(403, "This file was sent to another lender", "officer.scan_other_lender")
    if body.action == "request_documents" and not body.documents:
        raise ProblemError(422, "Say which papers are needed", "errors.validation")
    terms = _terms(app, body) if body.action == "approve" else None
    await apps.transition(session, principal, app, applicant, target, note=body.note, reason_code=body.reason_code,
                          requested_documents=body.documents or None)
    if terms:
        app.finance_summary = {**(app.finance_summary or {}), "sanction": {**terms, "decided_at": utcnow().isoformat(timespec="seconds")}}
        await session.flush()
        await _store_letter(session, app, applicant, terms, body.note, principal)
    return app


async def _store_letter(session: AsyncSession, app: Application, applicant: Applicant, terms: dict[str, Any], note: str | None,
                        principal: Principal) -> None:
    from app.modules.partner.letter import render_sanction_letter

    partner = await session.get(Partner, app.partner_id)
    ruleset = await apps.get_ruleset(session)
    code = app.eligibility_trace.get("scheme_code")
    doc = ruleset.schemes[code].doc if code in ruleset.schemes else {"name": {"en": code}}
    view = {
        "lang": app.lang, "tracking_id": app.tracking_id, "decided_on": utcnow().date().isoformat(),
        "applicant_name": applicant.full_name_enc or "—", "scheme_name": doc["name"].get(app.lang, doc["name"]["en"]),
        "partner": {"name": partner.name if partner else "—", "address": partner.address if partner else "",
                    "is_demo": bool(partner.is_demo) if partner else True},
        "terms": terms, "note": note, "officer_ref": str(principal.user_id)[:8],
    }
    storage = get_storage()
    qr_png = await storage.get(f"applications/{app.id}/qr.png") if await storage.exists(f"applications/{app.id}/qr.png") else None
    pdf = await asyncio.to_thread(render_sanction_letter, view, qr_png)
    await storage.put(f"applications/{app.id}/sanction-letter.pdf", pdf)
