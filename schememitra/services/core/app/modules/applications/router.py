from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, current_principal, require_roles
from app.core.storage import get_storage
from app.db.models import Applicant, Application, Consent, Partner
from app.db.session import get_session
from app.errors import ProblemError
from app.modules.applications import jobs as _jobs  # noqa: F401  (registers background jobs)
from app.modules.applications import service
from app.modules.applications.access import load_for, require_applicant_side
from app.modules.applications.schemas import (
    ApplicationOut,
    ConsentIn,
    DraftIn,
    ReadinessOut,
    SubmitOut,
    TrackOut,
)
from app.modules.documents.service import document_out

router = APIRouter(tags=["applications"])
Session = Annotated[AsyncSession, Depends(get_session)]
Me = Annotated[Principal, Depends(current_principal)]
ApplicantSide = Annotated[Principal, Depends(require_roles("citizen", "csc_operator", "admin"))]


async def application_out(session: AsyncSession, app: Application, applicant: Applicant) -> dict[str, Any]:
    partner = await session.get(Partner, app.partner_id) if app.partner_id else None
    docs = await service.documents_of(session, app)
    finance = app.finance_summary or {}
    return {
        "id": str(app.id), "tracking_id": app.tracking_id, "status": app.status,
        "scheme_code": (app.eligibility_trace or {}).get("scheme_code"), "partner_id": str(app.partner_id) if app.partner_id else None,
        "partner_name": partner.name if partner else None, "lang": app.lang, "submitted_via": app.submitted_via,
        "completeness_score": app.completeness_score, "eligibility_status": (app.eligibility_trace or {}).get("status"),
        "plan": finance.get("plan", {}), "finance": {k: v for k, v in finance.items() if k != "plan"},
        "requested_documents": app.requested_documents or [], "rejection_reason_code": app.rejection_reason_code,
        "timeline": service.timeline(app), "documents": [document_out(d) for d in docs.values()],
        "consent_recorded": applicant.consent_id is not None,
        "created_at": app.created_at.isoformat(timespec="seconds"),
        "submitted_at": app.submitted_at.isoformat(timespec="seconds") if app.submitted_at else None,
    }


@router.post("/v1/applications", response_model=ApplicationOut)
async def create_or_update(body: DraftIn, session: Session, me: ApplicantSide) -> Any:
    """Idempotent on client_uuid: offline clients can retry safely."""
    app = await service.upsert_draft(session, me, body)
    applicant = await session.get(Applicant, app.applicant_id)
    assert applicant is not None
    await session.commit()
    return await application_out(session, app, applicant)


@router.get("/v1/applications", response_model=list[ApplicationOut])
async def list_mine(session: Session, me: ApplicantSide) -> Any:
    query = select(Application).where(Application.deleted_at.is_(None)).order_by(Application.created_at.desc()).limit(50)
    if me.role == "citizen":
        query = query.join(Applicant, Applicant.id == Application.applicant_id).where(Applicant.user_id == me.user_id)
    elif me.role == "csc_operator":
        query = query.where(Application.created_by_user_id == me.user_id)
    out = []
    for app in (await session.execute(query)).scalars().all():
        applicant = await session.get(Applicant, app.applicant_id)
        assert applicant is not None
        out.append(await application_out(session, app, applicant))
    return out


@router.get("/v1/applications/{application_id}", response_model=ApplicationOut)
async def get_application(application_id: UUID, session: Session, me: Me) -> Any:
    app, applicant = await load_for(session, application_id, me)
    return await application_out(session, app, applicant)


@router.post("/v1/applications/{application_id}/readiness", response_model=ReadinessOut)
async def readiness(application_id: UUID, session: Session, me: Me) -> Any:
    app, applicant = await load_for(session, application_id, me)
    result = await service.readiness(session, app, applicant)
    await session.commit()
    return result


@router.post("/v1/applications/{application_id}/consent")
async def consent(application_id: UUID, body: ConsentIn, session: Session, me: Me) -> dict[str, Any]:
    require_applicant_side(me)
    app, applicant = await load_for(session, application_id, me, write=True)
    record = await service.record_consent(session, me, app, applicant, body)
    await session.commit()
    return {"consent_id": str(record.id), "granted_at": record.granted_at.isoformat(timespec="seconds")}


@router.post("/v1/applications/{application_id}/submit", response_model=SubmitOut)
async def submit(application_id: UUID, session: Session, me: Me) -> Any:
    require_applicant_side(me)
    app, applicant = await load_for(session, application_id, me, write=True)
    result = await service.submit(session, me, app, applicant)
    await session.commit()
    return result


@router.post("/v1/applications/{application_id}/resubmit", response_model=ApplicationOut)
async def resubmit(application_id: UUID, session: Session, me: Me) -> Any:
    require_applicant_side(me)
    app, applicant = await load_for(session, application_id, me, write=True)
    await service.transition(session, me, app, applicant, "resubmitted")
    await session.commit()
    return await application_out(session, app, applicant)


@router.get("/v1/applications/{application_id}/qr.png")
async def qr_png(application_id: UUID, session: Session, me: Me) -> Response:
    app, _ = await load_for(session, application_id, me)
    if app.submitted_at is None:
        raise ProblemError(404, "QR is created on submit", "errors.not_found")
    return Response(await get_storage().get(f"applications/{app.id}/qr.png"), media_type="image/png",
                    headers={"cache-control": "private, max-age=3600"})


@router.get("/v1/applications/{application_id}/loan-file.pdf")
async def loan_file(application_id: UUID, session: Session, me: Me) -> Response:
    app, _ = await load_for(session, application_id, me)
    if app.submitted_at is None:
        raise ProblemError(404, "Loan file is created on submit", "errors.not_found")
    storage = get_storage()
    key = f"applications/{app.id}/loan-file.pdf"
    if not await storage.exists(key):
        await _jobs.render_and_store(str(app.id))
    data = await storage.get(key)
    return Response(data, media_type="application/pdf",
                    headers={"content-disposition": f'inline; filename="{app.tracking_id}.pdf"', "cache-control": "private, no-store"})


@router.get("/v1/applications/{application_id}/sanction-letter.pdf")
async def sanction_letter(application_id: UUID, session: Session, me: Me) -> Response:
    """Issued by the lender on approval; readable by the applicant side and that lender."""
    app, _ = await load_for(session, application_id, me)
    key = f"applications/{app.id}/sanction-letter.pdf"
    storage = get_storage()
    if app.status not in ("sanctioned", "disbursed") or not await storage.exists(key):
        raise ProblemError(404, "No sanction letter for this application", "errors.not_found")
    return Response(await storage.get(key), media_type="application/pdf",
                    headers={"content-disposition": f'inline; filename="{app.tracking_id}-sanction.pdf"', "cache-control": "private, no-store"})


@router.post("/v1/applications/{application_id}/erase")
async def erase(application_id: UUID, session: Session, me: Me) -> dict[str, bool]:
    """Withdraw consent and delete personal data (DPDP Act 2023, right to erasure)."""
    require_applicant_side(me)
    app, applicant = await load_for(session, application_id, me, write=True)
    await service.erase(session, me, app, applicant)
    await session.commit()
    return {"erased": True}


@router.get("/v1/track/{tracking_id}", response_model=TrackOut)
async def track(tracking_id: Annotated[str, Path(min_length=10, max_length=24)], session: Session) -> Any:
    """Public status by tracking ID (no personal data), also used by SMS STATUS and IVR."""
    return await service.track(session, tracking_id)


@router.get("/v1/applications/{application_id}/consents")
async def consents(application_id: UUID, session: Session, me: Me) -> list[dict[str, Any]]:
    _, applicant = await load_for(session, application_id, me)
    rows = (await session.execute(select(Consent).where(Consent.applicant_id == applicant.id))).scalars().all()
    return [{"id": str(c.id), "method": c.method, "purpose": c.purpose, "language": c.language, "text_version": c.text_version,
             "granted_at": c.granted_at.isoformat(timespec="seconds"),
             "withdrawn_at": c.withdrawn_at.isoformat(timespec="seconds") if c.withdrawn_at else None} for c in rows]
