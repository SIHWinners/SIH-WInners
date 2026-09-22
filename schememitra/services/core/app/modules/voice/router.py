from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, optional_principal, require_roles
from app.db.session import get_session
from app.errors import not_found
from app.modules.applications.access import load_for
from app.modules.voice import service, speech
from app.modules.voice.schemas import ReadbackIn, ReadbackOut, ReadbackReplyOut, SessionIn, VoiceTurnOut

router = APIRouter(tags=["voice"])
Session = Annotated[AsyncSession, Depends(get_session)]
MaybeMe = Annotated[Principal | None, Depends(optional_principal)]
ApplicantSide = Annotated[Principal, Depends(require_roles("citizen", "csc_operator", "admin"))]


async def _read_audio(audio: UploadFile | None) -> tuple[bytes | None, str | None]:
    if audio is None:
        return None, None
    data = await audio.read(speech.MAX_AUDIO_BYTES + 1)
    return data, audio.content_type


@router.post("/v1/voice/sessions", response_model=VoiceTurnOut)
async def create_session(body: SessionIn, session: Session, me: MaybeMe) -> Any:
    """Start a guided voice intake. Works before sign-in, like the typed form."""
    out = await service.create_session(session, body.lang, me)
    await session.commit()
    return out


@router.get("/v1/voice/sessions/{session_id}", response_model=VoiceTurnOut)
async def get_session_state(session_id: Annotated[UUID, Path()], session: Session, me: MaybeMe) -> Any:
    conv = await service.get_conversation(session, session_id, me)
    return await service.current(session, conv)


@router.post("/v1/voice/sessions/{session_id}/utterance", response_model=VoiceTurnOut)
async def utterance(
    session_id: Annotated[UUID, Path()],
    session: Session,
    me: MaybeMe,
    text: Annotated[str | None, Form(max_length=500)] = None,
    audio: Annotated[UploadFile | None, File(description="≤15 s chunk: audio/webm (Opus), ogg, wav, mp4")] = None,
) -> Any:
    """One turn: audio (or typed text) → transcript → slots → localized reply (+ audio URL)."""
    conv = await service.get_conversation(session, session_id, me)
    data, content_type = await _read_audio(audio)
    out = await service.utterance(session, conv, text=text, audio=data, content_type=content_type)
    await session.commit()
    return out


@router.post("/v1/voice/readback", response_model=ReadbackOut)
async def readback(body: ReadbackIn, session: Session, me: ApplicantSide) -> Any:
    """Summary of the application in the applicant's language, to be read aloud before submit (C6)."""
    app, applicant = await load_for(session, UUID(body.application_id), me)
    return await service.readback(session, app, applicant)


@router.post("/v1/voice/readback/{application_id}/reply", response_model=ReadbackReplyOut)
async def readback_reply(
    application_id: Annotated[UUID, Path()],
    session: Session,
    me: ApplicantSide,
    text: Annotated[str | None, Form(max_length=500)] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> Any:
    """"haan, sahi hai" confirms (text evidence goes into the consent record); naming a field asks to correct it."""
    app, applicant = await load_for(session, application_id, me)
    data, content_type = await _read_audio(audio)
    return await service.readback_reply(session, app, applicant, text=text, audio=data, content_type=content_type)


@router.get("/v1/voice/tts/{digest}", responses={200: {"content": {"audio/wav": {}}}})
async def tts_clip(digest: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")]) -> Response:
    audio = await speech.cached_clip(digest)
    if audio is None:
        raise not_found("audio clip")
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "public, max-age=31536000, immutable"})
