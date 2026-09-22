"""Application lifecycle: draft → readiness → consent → submit → partner decisions → tracking.

The server never trusts client-side eligibility or maths: on every save and again at submit it
re-evaluates the published rules and rebuilds the repayment schedule from the plan."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import audit
from app.core.i18n import t
from app.core.ids import is_valid_tracking_id, new_tracking_id, normalize_tracking_id
from app.core.security import Principal
from app.core.storage import get_storage
from app.db.base import utcnow
from app.db.models import Applicant, Application, Consent, Document, Partner
from app.errors import ProblemError, conflict
from app.modules.analytics import events as analytics
from app.modules.applications import qr, status
from app.modules.applications.schemas import ConsentIn, DraftIn
from app.modules.documents.names import parse_name, phonetic_key
from app.modules.documents.readiness import Applicant as ReadinessApplicant
from app.modules.documents.readiness import DocView, check_readiness
from app.modules.eligibility.loader import get_ruleset
from app.modules.eligibility.service import evaluate_against
from app.modules.finance.calc import LoanInput, build_schedule, funding_split
from app.modules.notify.service import notify_status


def district_label(code: str | None) -> str | None:
    from app.modules.routing.districts import BY_CODE

    district = BY_CODE.get(code or "")
    return f"{district.name}, {district.state_code}" if district else code


def _now_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def _facts_of(applicant: Applicant) -> dict[str, Any]:
    profile = applicant.profile or {}
    return {
        "age": profile.get("age"), "gender": applicant.gender, "social_category": applicant.social_category,
        "has_disability": applicant.disability_flag, "disability_pct": applicant.disability_pct,
        "state_code": applicant.state_code, "district_code": applicant.district_code, "pincode": applicant.pincode,
        "annual_family_income_paise": applicant.annual_family_income_paise, "education_level": applicant.education_level,
        "occupation": applicant.occupation, "business_type": profile.get("business_type"),
        "project_cost_paise": profile.get("project_cost_paise"), "loan_needed_paise": profile.get("loan_needed_paise"),
        "existing_loans": profile.get("existing_loans"), "shg_member": profile.get("shg_member"),
        "course_admitted": profile.get("course_admitted"), "lat": applicant.lat, "lng": applicant.lng,
    }


async def _scheme_result(session: AsyncSession, facts: dict[str, Any], scheme_code: str) -> tuple[dict[str, Any], Any]:
    from app.modules.eligibility.schemas import ApplicantFacts

    ruleset = await get_ruleset(session)
    rules = ruleset.schemes.get(scheme_code)
    if rules is None:
        raise ProblemError(422, "Unknown scheme", "errors.validation", scheme_code)
    result = evaluate_against(ruleset, ApplicantFacts(**{k: v for k, v in facts.items() if v is not None}), [scheme_code])
    return result["results"][0], rules


def _finance(plan: dict[str, Any], rules: Any, project_cost: int | None) -> dict[str, Any]:
    schedule = build_schedule(LoanInput(plan["principal_paise"], plan["rate_bps"], plan["tenure_months"],
                                        plan["moratorium_months"], plan["treatment"], plan["frequency"]))
    fp = rules.doc["funding_pattern"]
    cost = project_cost if project_cost and project_cost >= plan["principal_paise"] else plan["principal_paise"]
    split = funding_split(cost, fp["apex_bps"], fp["partner_bps"], fp["beneficiary_bps"])
    return {
        "emi_paise": schedule.instalment_paise, "instalments": schedule.instalments, "period_months": schedule.period_months,
        "total_interest_paise": schedule.total_interest_paise, "total_payable_paise": schedule.total_payable_paise,
        "principal_after_moratorium_paise": schedule.principal_after_moratorium_paise, "split": split.__dict__,
    }


def _history(app: Application, new_status: str, actor: Principal | None, **extra: Any) -> None:
    entry = {"status": new_status, "at": _now_iso(), "by": actor.role if actor else "system", **extra}
    app.status_history = [*(app.status_history or []), entry]
    app.status = new_status


async def upsert_draft(session: AsyncSession, principal: Principal, body: DraftIn) -> Application:
    app = (await session.execute(select(Application).where(Application.client_uuid == body.client_uuid))).scalar_one_or_none()
    if app is not None:
        applicant = await session.get(Applicant, app.applicant_id)
        assert applicant is not None
        from app.modules.applications.access import can_access

        if not can_access(principal, app, applicant, write=True):
            raise conflict("client_uuid already used", "errors.conflict")
        if app.status not in ("draft", "ready"):
            return app  # idempotent replay after submit: nothing to change
    else:
        applicant = Applicant(user_id=principal.user_id if principal.role == "citizen" else None,
                              created_by_operator_id=principal.user_id if principal.role == "csc_operator" else None)
        session.add(applicant)
        await session.flush()

    partner = await session.get(Partner, UUID(body.partner_id))
    if partner is None or partner.deleted_at is not None:
        raise ProblemError(422, "Unknown partner", "errors.validation")
    if body.scheme_code not in partner.schemes_supported:
        raise ProblemError(422, "Partner does not offer this scheme", "partner.skip.scheme_unsupported")

    p, f = body.personal, body.facts.facts()
    if p.full_name:
        parsed = parse_name(p.full_name)
        applicant.full_name_enc = p.full_name
        applicant.name_normalized = parsed.normalized
        applicant.name_phonetic = " ".join(phonetic_key(tok) for tok in parsed.tokens)
    applicant.father_name_enc = p.father_name or applicant.father_name_enc
    applicant.dob_enc = p.dob.isoformat() if p.dob else applicant.dob_enc
    applicant.phone_enc = p.phone or applicant.phone_enc
    applicant.gender, applicant.social_category = f["gender"], f["social_category"]
    applicant.disability_flag, applicant.disability_pct = bool(f["has_disability"]), f["disability_pct"]
    applicant.state_code, applicant.district_code, applicant.pincode = f["state_code"], f["district_code"], f["pincode"]
    applicant.lat, applicant.lng = f["lat"], f["lng"]
    applicant.annual_family_income_paise = f["annual_family_income_paise"]
    applicant.education_level, applicant.occupation = f["education_level"], f["occupation"]
    applicant.profile = {k: f[k] for k in ("age", "business_type", "project_cost_paise", "loan_needed_paise",
                                           "existing_loans", "shg_member", "course_admitted")}

    result, rules = await _scheme_result(session, _facts_of(applicant), body.scheme_code)
    plan = body.plan.model_dump()
    if plan["principal_paise"] > rules.doc["loan_limits"]["max_paise"]:
        raise ProblemError(422, "Loan above scheme limit", "rules.c.loan_exceeds")

    if app is None:
        app = Application(tracking_id=new_tracking_id(f["state_code"] or "IN"), applicant_id=applicant.id,
                          client_uuid=body.client_uuid, created_by_user_id=principal.user_id, status="draft",
                          status_history=[{"status": "draft", "at": _now_iso(), "by": principal.role}])
        session.add(app)
        await audit.record(session, actor=principal.actor, actor_role=principal.role, action="application.created",
                           entity=f"application:{app.tracking_id}", diff={"scheme": body.scheme_code})
        await analytics.record(session, "application_started", step="speak_scan", lang=body.lang, facts=f,
                               scheme_code=body.scheme_code)
    scheme_row = rules.scheme_id
    app.scheme_id = UUID(scheme_row) if scheme_row else None
    app.rule_version_id = UUID(rules.rule_version_id) if rules.rule_version_id else None
    app.partner_id = partner.id
    app.lang = body.lang
    app.submitted_via = body.submitted_via
    app.requested_amount_paise = plan["principal_paise"]
    app.project_cost_paise = f["project_cost_paise"]
    app.tenure_months, app.moratorium_months, app.interest_rate_bps = plan["tenure_months"], plan["moratorium_months"], plan["rate_bps"]
    app.eligibility_trace = {"scheme_code": body.scheme_code, "status": result["status"], "trace": result["trace"],
                             "version": result["version"], "evaluated_at": _now_iso()}
    app.finance_summary = {"plan": plan, **_finance(plan, rules, f["project_cost_paise"])}
    await session.flush()
    return app


async def documents_of(session: AsyncSession, app: Application) -> dict[str, Document]:
    rows = (await session.execute(select(Document).where(Document.application_id == app.id)
                                  .order_by(Document.created_at))).scalars().all()
    return {d.type: d for d in rows}  # the latest upload of each type wins


async def readiness(session: AsyncSession, app: Application, applicant: Applicant) -> dict[str, Any]:
    _, rules = await _scheme_result(session, _facts_of(applicant), app.eligibility_trace["scheme_code"])
    docs = await documents_of(session, app)
    views = {t_: DocView(t_, {k: v for k, v in d.ocr_json.get("fields", {}).items() if k != "aadhaar_hash"},
                         d.confidence or 0.0, d.quality.get("issues", []), d.source, d.verified) for t_, d in docs.items()}
    result = check_readiness(
        rules.doc["documents_required"], views,
        ReadinessApplicant(applicant.full_name_enc, applicant.father_name_enc, applicant.dob_enc, app.project_cost_paise),
        get_settings().readiness_threshold,
    )
    app.completeness_score = result["score"]
    if app.status in ("draft", "ready"):
        target = "ready" if result["ready"] else "draft"
        if target != app.status:
            _history(app, target, None)
    return {**result, "required_documents": rules.doc["documents_required"]}


# Text-only evidence we keep with a consent (never audio). Anything else a client sends is dropped.
CONSENT_EVIDENCE_KEYS = ("readback_text", "confirmed_by", "otp_verified", "utterance", "thumb_slip_document_id",
                         "voice_confirmation", "transcript_engine", "confirmed_at", "language")


async def record_consent(session: AsyncSession, principal: Principal, app: Application, applicant: Applicant, body: ConsentIn) -> Consent:
    consent = Consent(applicant_id=applicant.id, purpose="loan_application", scope=body.scope, language=body.language,
                      method=body.method, text_version=body.text_version,
                      evidence={k: v for k, v in body.evidence.items() if k in CONSENT_EVIDENCE_KEYS},
                      captured_by_operator_id=principal.user_id if principal.role == "csc_operator" else None)
    session.add(consent)
    await session.flush()
    applicant.consent_id = consent.id
    await audit.record(session, actor=principal.actor, actor_role=principal.role, action="consent.granted",
                       entity=f"application:{app.tracking_id}", diff={"method": body.method, "version": body.text_version})
    return consent


def content_hash(app: Application, applicant: Applicant, docs: dict[str, Document]) -> str:
    snapshot = {"tid": app.tracking_id, "trace": app.eligibility_trace, "finance": app.finance_summary,
                "partner": str(app.partner_id), "name": applicant.name_normalized, "docs": sorted(d.sha256 for d in docs.values())}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


async def submit(session: AsyncSession, principal: Principal, app: Application, applicant: Applicant) -> dict[str, Any]:
    if app.status not in ("draft", "ready"):
        raise conflict("already submitted")
    result, _ = await _scheme_result(session, _facts_of(applicant), app.eligibility_trace["scheme_code"])
    if result["status"] != "eligible":
        raise ProblemError(422, "Not eligible under current rules", "rules.none_eligible", extra={"failed": result["failed"]})
    ready = await readiness(session, app, applicant)
    if not ready["ready"]:
        raise ProblemError(422, "File not ready", "send.not_ready", extra={"score": ready["score"], "blockers": ready["blockers"]})
    if applicant.consent_id is None:
        raise ProblemError(422, "Consent required", "send.consent_title")

    docs = await documents_of(session, app)
    app.content_hash = content_hash(app, applicant, docs)
    app.submitted_at = utcnow()
    _history(app, "submitted", principal)
    partner = await session.get(Partner, app.partner_id)
    token = qr.sign_qr(app.tracking_id, app.content_hash, str(app.partner_id))
    await get_storage().put(f"applications/{app.id}/qr.png", qr.qr_png(token))
    await audit.record(session, actor=principal.actor, actor_role=principal.role, action="application.submitted",
                       entity=f"application:{app.tracking_id}", diff={"partner": str(app.partner_id), "hash": app.content_hash[:16]})
    await analytics.record(session, "application_submitted", step="send_track", lang=app.lang, facts=_facts_of(applicant),
                           scheme_code=app.eligibility_trace["scheme_code"], partner_type=partner.type if partner else None)
    await notify_status(session, app, applicant, partner)
    await session.flush()
    from app.core.jobs import get_queue

    await get_queue().enqueue("render_loan_file", application_id=str(app.id))
    return {"tracking_id": app.tracking_id, "status": app.status, "qr_token": token,
            "qr_png_url": f"/api/v1/applications/{app.id}/qr.png", "loan_file_pdf_url": f"/api/v1/applications/{app.id}/loan-file.pdf"}


async def transition(session: AsyncSession, principal: Principal, app: Application, applicant: Applicant, target: str,
                     *, note: str | None = None, reason_code: str | None = None, requested_documents: list[str] | None = None) -> None:
    role = principal.role
    if not status.can_transition(app.status, target, role):
        raise conflict(f"cannot move from {app.status} to {target}", "errors.conflict")
    extra: dict[str, Any] = {}
    if target == "rejected":
        if reason_code not in status.REJECT_REASONS:
            raise ProblemError(422, "Reason code required", "errors.validation")
        app.rejection_reason_code = reason_code
        extra["reason_code"] = reason_code
    if target == "documents_requested":
        app.requested_documents = requested_documents or []
        extra["documents"] = app.requested_documents
    if target in ("sanctioned", "rejected"):
        app.decided_at = utcnow()
    if note:
        extra["note"] = note[:500]
    previous = app.status
    _history(app, target, principal, **extra)
    await audit.record(session, actor=principal.actor, actor_role=role, action=f"application.{target}",
                       entity=f"application:{app.tracking_id}", diff={"from": previous, **extra})
    facts = _facts_of(applicant)
    value = None
    if target in ("sanctioned", "rejected") and app.submitted_at:
        value = round((utcnow() - app.submitted_at).total_seconds() / 86400, 2)
    partner = await session.get(Partner, app.partner_id)
    await analytics.record(session, f"application_{target}", step="send_track", lang=app.lang, facts=facts,
                           scheme_code=app.eligibility_trace.get("scheme_code"), partner_type=partner.type if partner else None,
                           reason_code=reason_code, value=value)
    await notify_status(session, app, applicant, partner)


def timeline(app: Application) -> list[dict[str, Any]]:
    items = []
    for entry in app.status_history or []:
        params = {}
        if entry.get("documents"):
            params["docs"] = entry["documents"]
        if entry.get("reason_code"):
            params["reason_code"] = entry["reason_code"]
        items.append({"status": entry["status"], "at": entry["at"], "note_key": f"track.status.{entry['status']}", "params": params})
    return items


async def track(session: AsyncSession, raw_tid: str) -> dict[str, Any]:
    tid = normalize_tracking_id(raw_tid)
    if not is_valid_tracking_id(tid):
        raise ProblemError(422, "Tracking ID check failed", "track.invalid_id")
    app = (await session.execute(select(Application).where(Application.tracking_id == tid))).scalar_one_or_none()
    if app is None or app.deleted_at is not None:
        raise ProblemError(404, "Not found", "errors.track_not_found")
    partner = await session.get(Partner, app.partner_id) if app.partner_id else None
    from app.modules.routing.service import latest_metrics

    metrics = (await latest_metrics(session, [partner.id])).get(partner.id) if partner else None
    return {
        "tracking_id": app.tracking_id, "status": app.status, "scheme_code": (app.eligibility_trace or {}).get("scheme_code"),
        "partner_name": partner.name if partner else None, "partner_type": partner.type if partner else None,
        "expected_days": round(metrics.avg_sanction_days) if metrics else None, "timeline": timeline(app),
        "next_step_key": f"track.next.{app.status}", "requested_documents": app.requested_documents or [],
        "rejection_reason_code": app.rejection_reason_code, "lang": app.lang,
    }


async def loan_file_view(session: AsyncSession, app: Application, applicant: Applicant) -> dict[str, Any]:
    from app.modules.analytics.events import age_from

    lang = app.lang
    partner = await session.get(Partner, app.partner_id)
    result, rules = await _scheme_result(session, _facts_of(applicant), app.eligibility_trace["scheme_code"])
    docs = await documents_of(session, app)
    ready = await readiness(session, app, applicant)
    consent = await session.get(Consent, applicant.consent_id) if applicant.consent_id else None
    phone = applicant.phone_enc or ""
    finance = app.finance_summary
    return {
        "lang": lang, "tracking_id": app.tracking_id,
        "submitted_at": (app.submitted_at or utcnow()).date().isoformat(), "content_hash": app.content_hash or "",
        "applicant": {
            "full_name": applicant.full_name_enc, "age": (applicant.profile or {}).get("age") or age_from(applicant.dob_enc),
            "gender_label": t(lang, f"options.gender.{applicant.gender}") if applicant.gender else None,
            "category_label": t(lang, f"options.social_category.{applicant.social_category}") if applicant.social_category else None,
            "district": district_label(applicant.district_code), "income_paise": applicant.annual_family_income_paise,
            "education_label": t(lang, f"options.education.{applicant.education_level}") if applicant.education_level else None,
            "phone_masked": f"******{phone[-4:]}" if phone else None, "project_cost_paise": app.project_cost_paise,
        },
        "scheme": {"name_en": rules.doc["name"]["en"], "name_local": rules.doc["name"].get(lang, rules.doc["name"]["en"]),
                   "apex_corp": rules.doc["apex_corp"], "version": result["version"], "trace": result["trace"],
                   "source_url": rules.doc["source_url"], "needs_verification": rules.doc["needs_verification"]},
        "plan": {**finance["plan"], **{k: finance[k] for k in ("emi_paise", "total_interest_paise", "total_payable_paise")}},
        "split": finance["split"],
        "partner": {"name": partner.name if partner else "—", "address": partner.address if partner else "", "type": partner.type if partner else "SCA"},
        "documents": [{"type": d.type, "source": d.source, "verified": d.verified, "status": d.quality.get("status", "ok"),
                       "confidence": d.confidence or 0.0, "sha256": d.sha256} for d in docs.values()],
        "readiness": ready,
        "consent": {"method": consent.method if consent else "—", "granted_at": consent.granted_at.isoformat(timespec="minutes") if consent else "—",
                    "language": consent.language if consent else lang, "text_version": consent.text_version if consent else "—"},
    }


async def erase(session: AsyncSession, principal: Principal, app: Application, applicant: Applicant) -> None:
    """DPDP right to erasure: delete stored images and PII, keep only the audit entry and
    already-anonymised analytics. The tracking ID stops resolving."""
    storage = get_storage()
    for doc in (await session.execute(select(Document).where(Document.application_id == app.id))).scalars():
        if doc.storage_key:
            await storage.delete(doc.storage_key)
        doc.storage_key, doc.ocr_json, doc.purged_at = None, {}, utcnow()
    for key in ("qr.png", "loan-file.pdf"):
        await storage.delete(f"applications/{app.id}/{key}")
    for field in ("full_name_enc", "father_name_enc", "dob_enc", "phone_enc", "address_enc", "name_normalized",
                  "name_phonetic", "aadhaar_last4", "aadhaar_hash"):
        setattr(applicant, field, None)
    applicant.lat = applicant.lng = None
    applicant.profile = {}
    applicant.deleted_at = app.deleted_at = utcnow()
    if applicant.consent_id:
        consent = await session.get(Consent, applicant.consent_id)
        if consent:
            consent.withdrawn_at = utcnow()
    await audit.record(session, actor=principal.actor, actor_role=principal.role, action="application.erased",
                       entity=f"application:{app.tracking_id}", diff={})


PURGE_AFTER = timedelta(hours=get_settings().image_purge_hours)


def purge_deadline() -> datetime:
    return datetime.now(UTC) + PURGE_AFTER
