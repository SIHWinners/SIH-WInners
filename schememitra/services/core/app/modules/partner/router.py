from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, require_roles
from app.db.session import get_session
from app.modules.partner import service
from app.modules.partner.schemas import DecisionIn, QueueOut, ReviewOut, ScanIn, ScanOut

router = APIRouter(tags=["partner"])
Session = Annotated[AsyncSession, Depends(get_session)]
Officer = Annotated[Principal, Depends(require_roles("partner_officer", "admin"))]


@router.get("/v1/partner/queue", response_model=QueueOut)
async def queue(session: Session, me: Officer, group: Literal["all", "new", "in_review", "decided"] = "all",
                q: Annotated[str | None, Query(max_length=60)] = None) -> Any:
    """Files sent to this lender. Admins see all lenders (read-only for decisions)."""
    return await service.queue(session, me, group, q)


@router.post("/v1/partner/scan", response_model=ScanOut)
async def scan(body: ScanIn, session: Session, me: Officer) -> Any:
    """Verify the signed QR from the citizen's phone or loan file, then open that file."""
    out = await service.scan(session, me, body.jws)
    await session.commit()
    return out


@router.get("/v1/partner/applications/{application_id}", response_model=ReviewOut)
async def review(application_id: UUID, session: Session, me: Officer) -> Any:
    out = await service.review(session, me, application_id)
    await session.commit()  # readiness refresh may update the completeness score
    return out


@router.post("/v1/partner/applications/{application_id}/decision", response_model=ReviewOut)
async def decision(application_id: UUID, body: DecisionIn, session: Session, me: Officer) -> Any:
    """receive · start_review · request_documents · approve (sanction letter) · reject (coded reason) · disburse.
    Status push and SMS in the applicant's language go out when this commits (claim C21: the lender decides)."""
    await service.decide(session, me, application_id, body)
    await session.commit()
    return await service.review(session, me, application_id)
