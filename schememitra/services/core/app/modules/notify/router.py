from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_internal
from app.db.session import get_session
from app.modules.notify import inbound
from app.modules.notify.sms import CONSOLE_FEED

router = APIRouter(tags=["notify"])
Session = Annotated[AsyncSession, Depends(get_session)]
Internal = Annotated[None, Depends(require_internal)]


class InboundSmsIn(BaseModel):
    from_: str = Field(alias="from", max_length=20)
    text: str = Field(max_length=2000)
    provider: Literal["console", "msg91", "twilio"] = "console"

    model_config = {"populate_by_name": True}


class InboundSmsOut(BaseModel):
    understood: Literal["apply", "status", "help", "partial", "unknown"]
    created: bool | None = None
    found: bool | None = None
    tracking_id: str | None = None
    reply_key: str | None = None
    body: str | None = None
    segments: int | None = None
    ref: str | None = None
    received: list[int] | None = None
    expected: int | None = None
    reason: str | None = None


class IvrIn(BaseModel):
    tracking_id: str | None = Field(default=None, max_length=24)
    lang: str = Field(default="hi", max_length=8)


class IvrOut(BaseModel):
    say: str
    expect: Literal["tracking_id", "end"]
    lang: str
    status: str | None = None
    partner: str | None = None


@router.post("/v1/sms/inbound", response_model=InboundSmsOut)
async def sms_inbound(body: InboundSmsIn, session: Session, _: Internal) -> Any:
    """Called by the gateway's SMS webhook. Reassembles multi-part messages, then answers
    STATUS lookups and creates SMS applications (claims C13, C14)."""
    out = await inbound.handle(session, body.from_, body.text, body.provider)
    await session.commit()
    return out


@router.post("/v1/ivr/next", response_model=IvrOut)
async def ivr_next(body: IvrIn, session: Session, _: Internal) -> Any:
    """IVR stub: the words the voice line reads back for a tracking ID."""
    return await inbound.ivr_menu(session, body.tracking_id, body.lang)


@router.get("/v1/admin/sms/console")
async def sms_console(limit: int = 50) -> dict[str, Any]:
    """Messages the console SMS adapter 'sent', newest last — the demo's SMS phone (SANDBOX)."""
    items = list(CONSOLE_FEED)[-limit:]
    return {"sandbox": True, "items": items}
