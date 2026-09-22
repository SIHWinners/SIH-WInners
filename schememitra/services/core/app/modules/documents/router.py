from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import Principal, current_principal
from app.core.storage import get_storage
from app.db.models import Document
from app.db.session import get_session
from app.errors import ProblemError, not_found
from app.modules.applications.access import load_for
from app.modules.documents import service
from app.modules.documents.digilocker import get_digilocker
from app.modules.documents.extract import DOC_TYPES
from app.modules.documents.ocr import DEMO_DOCS_DIR
from app.modules.documents.quality import MAX_UPLOAD_BYTES

router = APIRouter(tags=["documents"])
Session = Annotated[AsyncSession, Depends(get_session)]
Me = Annotated[Principal, Depends(current_principal)]


class DocumentOut(BaseModel):
    document_id: str
    type: str
    source: str
    fields: dict[str, Any]
    confidence: float
    issues: list[str]
    status: str
    suggest_digilocker: bool
    verified: bool
    sandbox: bool
    engine: str | None
    sha256: str
    purge_after: str | None


@router.post("/v1/documents", response_model=DocumentOut)
async def upload_document(
    session: Session, me: Me,
    application_id: Annotated[UUID, Form()],
    doc_type: Annotated[str, Form(max_length=32)],
    file: Annotated[UploadFile, File()],
    source: Annotated[Literal["camera", "upload"], Form()] = "camera",
) -> Any:
    app, applicant = await load_for(session, application_id, me, write=True)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    doc = await service.upload(session, me, app, applicant, doc_type, source, data)
    await session.commit()
    return service.document_out(doc)


class ConsentTokenIn(BaseModel):
    code: str


@router.post("/v1/documents/digilocker/consent")
async def digilocker_consent(body: ConsentTokenIn, me: Me) -> dict[str, Any]:
    """Exchanges the DigiLocker authorization code for a short-lived access token."""
    adapter = get_digilocker()
    return {"consent_token": await adapter.exchange(body.code), "sandbox": get_settings().digilocker_mode != "real"}


@router.get("/v1/documents/digilocker/authorize")
async def digilocker_authorize(me: Me, state: str) -> dict[str, Any]:
    return {"authorize_url": get_digilocker().authorize_url(state), "sandbox": get_settings().digilocker_mode != "real"}


class PullIn(BaseModel):
    application_id: UUID
    doc_type: str
    consent_token: str


@router.post("/v1/documents/digilocker/pull", response_model=DocumentOut)
async def digilocker_pull(body: PullIn, session: Session, me: Me) -> Any:
    if body.doc_type not in DOC_TYPES:
        raise ProblemError(422, "Unknown document type", "errors.validation")
    app, applicant = await load_for(session, body.application_id, me, write=True)
    doc = await service.pull_from_digilocker(session, me, app, applicant, body.doc_type, body.consent_token)
    await session.commit()
    return service.document_out(doc)


@router.get("/v1/documents/{document_id}/image")
async def document_image(document_id: UUID, session: Session, me: Me) -> Response:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise not_found("document")
    await load_for(session, doc.application_id, me)
    if not doc.storage_key:
        raise ProblemError(410, "Image purged after verification", "errors.not_found")
    data = await get_storage().get(doc.storage_key)
    return Response(data, media_type="image/jpeg", headers={"cache-control": "private, no-store"})


@router.get("/v1/demo/documents/{persona}/{doc_type}")
async def demo_document(persona: Annotated[str, Path(pattern=r"^[a-z]+$")], doc_type: Annotated[str, Path(pattern=r"^[a-z_]+$")],
                        variant: Literal["paper", "digilocker"] = "paper") -> Response:
    """Fictional demo papers for judges (DEMO_MODE only)."""
    if not get_settings().demo_mode:
        raise not_found("document")
    path = DEMO_DOCS_DIR / persona / ("digilocker" if variant == "digilocker" else "") / f"{doc_type}.png"
    if not path.exists():
        raise not_found("document")
    return Response(path.read_bytes(), media_type="image/png", headers={"cache-control": "no-store"})


@router.get("/v1/demo/documents/{persona}")
async def demo_document_list(persona: Annotated[str, Path(pattern=r"^[a-z]+$")]) -> dict[str, list[str]]:
    if not get_settings().demo_mode or not (DEMO_DOCS_DIR / persona).exists():
        raise not_found("persona")
    return {"documents": sorted(p.stem for p in (DEMO_DOCS_DIR / persona).glob("*.png"))}
