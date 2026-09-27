from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, require_roles
from app.db.base import utcnow
from app.db.models import Applicant, Application, Consent, Partner
from app.db.session import get_session
from app.modules.eligibility.loader import get_ruleset

router = APIRouter(tags=["csc"])
Session = Annotated[AsyncSession, Depends(get_session)]
Operator = Annotated[Principal, Depends(require_roles("csc_operator", "admin"))]


class CscItem(BaseModel):
    id: str
    tracking_id: str | None
    applicant_name: str
    phone_masked: str | None
    status: str
    scheme_name: str | None
    partner_name: str | None
    amount_paise: int | None
    readiness_score: int | None
    consent_method: str | None
    created_at: str
    lang: str


class CscQueueOut(BaseModel):
    items: list[CscItem]
    counts: dict[str, int]
    operator: str | None


@router.get("/v1/csc/queue", response_model=CscQueueOut)
async def queue(session: Session, me: Operator, days: Annotated[int, Query(ge=1, le=30)] = 1) -> Any:
    """Applicants this operator helped, newest first — the counter's day view (C15)."""
    since = utcnow() - timedelta(days=days)
    query = select(Application).where(Application.deleted_at.is_(None), Application.created_at >= since)
    if me.role == "csc_operator":
        query = query.where(Application.created_by_user_id == me.user_id)
    rows = (await session.execute(query.order_by(Application.created_at.desc()).limit(200))).scalars().all()
    ruleset = await get_ruleset(session)

    items, counts = [], {"all": 0, "draft": 0, "sent": 0, "decided": 0}
    for app in rows:
        applicant = await session.get(Applicant, app.applicant_id)
        assert applicant is not None
        partner = await session.get(Partner, app.partner_id) if app.partner_id else None
        code = (app.eligibility_trace or {}).get("scheme_code")
        scheme = ruleset.schemes.get(code) if code else None
        consent = await session.get(Consent, applicant.consent_id) if applicant.consent_id else None
        phone = applicant.phone_enc or ""
        counts["all"] += 1
        counts["draft" if app.status in ("draft", "ready") else "decided" if app.status in ("sanctioned", "rejected", "disbursed") else "sent"] += 1
        items.append({
            "id": str(app.id), "tracking_id": app.tracking_id, "applicant_name": applicant.full_name_enc or "—",
            "phone_masked": f"******{phone[-4:]}" if phone else None, "status": app.status,
            "scheme_name": scheme.doc["name"]["en"] if scheme else code, "partner_name": partner.name if partner else None,
            "amount_paise": (app.finance_summary or {}).get("plan", {}).get("principal_paise"),
            "readiness_score": app.completeness_score, "consent_method": consent.method if consent else None,
            "created_at": app.created_at.isoformat(timespec="minutes"), "lang": app.lang,
        })
    return {"items": items, "counts": counts, "operator": me.csc_id}
