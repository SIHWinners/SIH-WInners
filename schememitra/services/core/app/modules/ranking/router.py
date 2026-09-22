from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.eligibility import service as eligibility
from app.modules.eligibility.schemas import RankRequest, RankResponse

router = APIRouter(tags=["ranking"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/v1/ranking/rank", response_model=RankResponse)
async def rank(body: RankRequest, session: Session) -> Any:
    """Order the schemes the rules found eligible, with plain-language reasons. Never adds or removes a scheme."""
    out = await eligibility.evaluate(session, body.applicant, body.scheme_codes)
    by_code = {r["code"]: r for r in out["results"]}
    ranked = [{"code": code, **{k: by_code[code]["rank"][k] for k in ("position", "score", "reasons")}} for code in out["eligible"]]
    return {"method": out["ranking_method"], "ranked": ranked}
