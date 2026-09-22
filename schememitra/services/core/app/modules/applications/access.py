"""Who may see or change an application. Mirrors the Postgres RLS policies so SQLite (local
profile) enforces the same rules in code (ADR-001)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.db.models import Applicant, Application
from app.errors import forbidden, not_found


async def load_for(session: AsyncSession, application_id: UUID, principal: Principal, *, write: bool = False
                   ) -> tuple[Application, Applicant]:
    app = await session.get(Application, application_id)
    if app is None or app.deleted_at is not None:
        raise not_found("application")
    applicant = await session.get(Applicant, app.applicant_id)
    assert applicant is not None
    if not can_access(principal, app, applicant, write=write):
        # Same 404 as a missing row: never confirm that someone else's application exists.
        raise not_found("application")
    return app, applicant


def can_access(principal: Principal, app: Application, applicant: Applicant, *, write: bool = False) -> bool:
    if principal.role == "admin":
        return True
    if principal.role == "citizen":
        return applicant.user_id == principal.user_id
    if principal.role == "csc_operator":
        return app.created_by_user_id == principal.user_id
    if principal.role == "partner_officer":
        return not write and app.partner_id == principal.partner_id and app.status not in ("draft", "ready")
    return False


def require_applicant_side(principal: Principal) -> None:
    if principal.role not in ("citizen", "csc_operator", "admin"):
        raise forbidden("only the applicant or their CSC operator can do this")
