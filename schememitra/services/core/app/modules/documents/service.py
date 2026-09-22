"""Document intake: sanitize → quality → OCR → field templates → Aadhaar protection → encrypted
storage with a purge deadline. Only extracted fields and hashes outlive the purge window."""

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.security import Principal
from app.core.storage import get_storage
from app.db.base import utcnow
from app.db.models import Applicant, Application, Document
from app.errors import ProblemError
from app.modules.applications.service import purge_deadline
from app.modules.documents import aadhaar
from app.modules.documents.digilocker import get_digilocker
from app.modules.documents.extract import DOC_TYPES, extract_fields
from app.modules.documents.ocr import OcrLine, OcrResult, read_document
from app.modules.documents.quality import UploadRejected, sanitize_and_inspect

LOW_CONFIDENCE = 0.6


def document_out(doc: Document) -> dict[str, Any]:
    fields = {k: v for k, v in (doc.ocr_json.get("fields") or {}).items() if k != "aadhaar_hash"}
    return {
        "document_id": str(doc.id), "type": doc.type, "source": doc.source, "fields": fields,
        "confidence": doc.confidence or 0.0, "issues": doc.quality.get("issues", []), "status": doc.quality.get("status", "ok"),
        "suggest_digilocker": doc.quality.get("status") in ("retake", "low_confidence") and doc.type in
        ("caste_certificate", "income_certificate", "disability_certificate", "marksheet"),
        "verified": doc.verified, "sandbox": bool(doc.ocr_json.get("sandbox")), "engine": doc.ocr_json.get("engine"),
        "sha256": doc.sha256, "purge_after": doc.purge_after.isoformat() if doc.purge_after else None,
    }


async def _store(session: AsyncSession, app: Application, applicant: Applicant, doc_type: str, source: str,
                 original_sha: str, image: bytes | None, ocr: OcrResult, quality_issues: list[str], quality_metrics: dict[str, Any],
                 verified: bool = False) -> Document:
    extraction = extract_fields(doc_type, ocr)
    issues = [*quality_issues, *extraction.issues]
    if extraction.aadhaar_boxes and image is not None:
        image = aadhaar.mask_digits(image, extraction.aadhaar_boxes)
    if extraction.fields.get("aadhaar_last4"):
        applicant.aadhaar_last4 = extraction.fields["aadhaar_last4"]
        applicant.aadhaar_hash = extraction.fields["aadhaar_hash"]
    confidence = 1.0 if verified else extraction.confidence
    status = "ok"
    if quality_issues:
        status = "retake"
    elif confidence < LOW_CONFIDENCE:
        status = "low_confidence"

    doc = Document(application_id=app.id, type=doc_type, source=source, sha256=original_sha,
                   ocr_json={"fields": extraction.fields, "field_confidence": extraction.field_confidence,
                             "engine": ocr.engine, "sandbox": ocr.sandbox},
                   confidence=confidence, quality={**quality_metrics, "issues": issues, "status": status},
                   verified=verified, purge_after=purge_deadline())
    session.add(doc)
    await session.flush()
    if image is not None:
        doc.storage_key = f"docs/{app.id}/{doc.id}.jpg"
        await get_storage().put(doc.storage_key, image)
    return doc


async def upload(session: AsyncSession, principal: Principal, app: Application, applicant: Applicant, doc_type: str,
                 source: str, data: bytes) -> Document:
    if doc_type not in DOC_TYPES:
        raise ProblemError(422, "Unknown document type", "errors.validation")
    if app.status not in ("draft", "ready", "documents_requested"):
        raise ProblemError(409, "Application is locked", "errors.conflict")
    try:
        check = sanitize_and_inspect(data)
    except UploadRejected as err:
        raise ProblemError(415 if err.key == "errors.unsupported_file" else 413, "Upload rejected", err.key) from err
    original_sha = hashlib.sha256(data).hexdigest()
    ocr = await read_document(data, original_sha)
    doc = await _store(session, app, applicant, doc_type, source, original_sha, check.sanitized, ocr, check.issues,
                       {"blur_variance": check.blur_variance, "glare_ratio": check.glare_ratio, "brightness": check.brightness,
                        "width": check.width, "height": check.height})
    await audit.record(session, actor=principal.actor, actor_role=principal.role, action="document.uploaded",
                       entity=f"application:{app.tracking_id}", diff={"type": doc_type, "status": doc.quality["status"]})
    return doc


def persona_hint(applicant: Applicant) -> str | None:
    """Sandbox DigiLocker only holds certificates for the fictional demo personas."""
    from app.seed.personas import PERSONAS

    phone = applicant.phone_enc or ""
    return next((p.key for p in PERSONAS.values() if p.phone == phone), None)


async def pull_from_digilocker(session: AsyncSession, principal: Principal, app: Application, applicant: Applicant,
                               doc_type: str, consent_token: str) -> Document:
    pulled = await get_digilocker().pull_document(doc_type, consent_token, persona_hint(applicant))
    ocr = OcrResult([OcrLine(ln["text"], ln["confidence"], tuple(ln["box"])) for ln in pulled.lines], "digilocker", pulled.sandbox)
    image = None
    if pulled.image and pulled.image[:4] != b"%PDF":
        image = sanitize_and_inspect(pulled.image).sanitized
    doc = await _store(session, app, applicant, doc_type, "digilocker", hashlib.sha256(pulled.image or pulled.uri.encode()).hexdigest(),
                       image, ocr, [], {"issuer": pulled.issuer, "uri": pulled.uri}, verified=True)
    if not doc.ocr_json["fields"] and pulled.fields:
        doc.ocr_json = {**doc.ocr_json, "fields": pulled.fields}
    await audit.record(session, actor=principal.actor, actor_role=principal.role, action="document.digilocker_pulled",
                       entity=f"application:{app.tracking_id}", diff={"type": doc_type, "sandbox": pulled.sandbox})
    return doc


async def purge_expired(session: AsyncSession) -> int:
    """Deletes raw images past their purge deadline; fields and hashes stay for the partner."""
    from sqlalchemy import select

    now = utcnow()
    rows = (await session.execute(select(Document).where(Document.purge_after < now, Document.purged_at.is_(None),
                                                         Document.storage_key.is_not(None)))).scalars().all()
    storage = get_storage()
    for doc in rows:
        await storage.delete(doc.storage_key or "")
        doc.storage_key, doc.purged_at = None, now
    return len(rows)
