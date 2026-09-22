from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.eligibility import service
from app.modules.eligibility.loader import get_ruleset
from app.modules.eligibility.schemas import EvaluateRequest, EvaluateResponse

router = APIRouter(tags=["eligibility"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/v1/eligibility/evaluate", response_model=EvaluateResponse)
async def evaluate(body: EvaluateRequest, session: Session) -> Any:
    """Rules-only eligibility with a full, localisable trace for every scheme."""
    return await service.evaluate(session, body.applicant, body.scheme_codes)


@router.get("/v1/rules/bundle")
async def rules_bundle(request: Request, response: Response, session: Session) -> Any:
    """Versioned rule set for offline evaluation on phones. Honours If-None-Match."""
    bundle = (await get_ruleset(session)).bundle()
    etag = f'"{bundle["etag"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"etag": etag})
    response.headers["etag"] = etag
    response.headers["cache-control"] = "public, max-age=300, stale-while-revalidate=86400"
    return bundle
