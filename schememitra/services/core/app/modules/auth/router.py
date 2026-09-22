from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, current_principal
from app.db.models import User
from app.db.session import get_session
from app.errors import not_found
from app.modules.auth import service

router = APIRouter(prefix="/v1/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]


class OtpRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=16, examples=["9876500001"])


class OtpRequestResponse(BaseModel):
    sent: bool
    ttl_seconds: int
    channel: str
    dev_otp: str | None = None


class OtpVerify(BaseModel):
    phone: str = Field(min_length=10, max_length=16)
    code: str = Field(min_length=4, max_length=8)
    lang: str = Field(default="en", max_length=8)


class SessionUser(BaseModel):
    id: str
    role: str
    partner_id: str | None = None
    csc_id: str | None = None
    display_name: str | None = None
    preferred_lang: str = "en"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: SessionUser


@router.post("/otp/request", response_model=OtpRequestResponse)
async def otp_request(body: OtpRequest, session: Session) -> Any:
    return await service.request_otp(session, body.phone)


@router.post("/otp/verify", response_model=TokenResponse)
async def otp_verify(body: OtpVerify, session: Session) -> Any:
    return await service.verify_otp(session, body.phone, body.code, body.lang)


@router.get("/me", response_model=SessionUser)
async def me(session: Session, principal: Annotated[Principal, Depends(current_principal)]) -> Any:
    user = await session.get(User, principal.user_id)
    if not user:
        raise not_found("user")
    return SessionUser(id=str(user.id), role=user.role, partner_id=str(user.partner_id) if user.partner_id else None,
                       csc_id=user.csc_id, display_name=user.display_name, preferred_lang=user.preferred_lang)
