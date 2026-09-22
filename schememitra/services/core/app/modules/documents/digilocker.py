"""DigiLocker adapter (spec §9.2, claim C10). A torn or faded paper certificate is replaced by
the issuer-signed copy from the citizen's DigiLocker, fetched only with their consent.

- SandboxDigiLocker (DIGILOCKER_MODE=sandbox): serves clean certificates seeded for demo personas.
- RealDigiLocker (DIGILOCKER_MODE=real): OAuth2 partner flow — authorize URL, code→token exchange,
  list issued documents, fetch the matching file. Needs approved partner credentials."""

import json
import secrets
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.errors import ProblemError
from app.modules.documents.ocr import DEMO_DOCS_DIR

# DigiLocker issued-document type codes for what our schemes need (verify during onboarding).
DOC_TYPE_CODES = {
    "caste_certificate": "CASCER", "income_certificate": "INCCER", "disability_certificate": "DSCER",
    "marksheet": "HSCER", "aadhaar": "ADHAR",
}


@dataclass
class PulledDocument:
    doc_type: str
    fields: dict[str, Any]
    lines: list[dict[str, Any]]
    image: bytes | None
    issuer: str
    uri: str
    sandbox: bool


class DigiLockerAdapter(Protocol):
    def authorize_url(self, state: str) -> str: ...
    async def exchange(self, code: str) -> str: ...
    async def pull_document(self, doc_type: str, consent_token: str, persona_hint: str | None) -> PulledDocument: ...


class SandboxDigiLocker:
    """Consent is simulated: `authorize_url` returns an in-app page and any code exchanges for a token."""

    def authorize_url(self, state: str) -> str:
        return f"/digilocker/sandbox?{urlencode({'state': state})}"

    async def exchange(self, code: str) -> str:
        return f"sandbox-{secrets.token_urlsafe(12)}"

    async def pull_document(self, doc_type: str, consent_token: str, persona_hint: str | None) -> PulledDocument:
        if not consent_token.startswith("sandbox-"):
            raise ProblemError(401, "DigiLocker consent missing", "errors.unauthorized")
        path = DEMO_DOCS_DIR / (persona_hint or "_none") / "digilocker" / f"{doc_type}.json"
        if not path.exists():
            raise ProblemError(404, "No such document in DigiLocker (sandbox)", "errors.not_found")
        record = json.loads(path.read_text(encoding="utf-8"))
        image_path = path.with_suffix(".png")
        return PulledDocument(doc_type, record["fields"], record["lines"],
                              image_path.read_bytes() if image_path.exists() else None,
                              record["issuer"], record["uri"], True)


class RealDigiLocker:
    BASE = "https://digilocker.meripehchaan.gov.in/public/oauth2"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.digilocker_client_id and s.digilocker_client_secret):
            raise ProblemError(503, "DigiLocker is not configured", "errors.server_down")
        self.client_id, self.secret, self.redirect = s.digilocker_client_id, s.digilocker_client_secret, s.digilocker_redirect_uri

    def authorize_url(self, state: str) -> str:
        return f"{self.BASE}/1/authorize?" + urlencode(
            {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect, "state": state}
        )

    async def exchange(self, code: str) -> str:
        async with httpx.AsyncClient(timeout=get_settings().external_timeout_s) as client:
            res = await client.post(f"{self.BASE}/1/token", data={
                "code": code, "grant_type": "authorization_code", "client_id": self.client_id,
                "client_secret": self.secret, "redirect_uri": self.redirect,
            })
            res.raise_for_status()
            return str(res.json()["access_token"])

    async def pull_document(self, doc_type: str, consent_token: str, persona_hint: str | None) -> PulledDocument:
        headers = {"Authorization": f"Bearer {consent_token}"}
        async with httpx.AsyncClient(timeout=get_settings().external_timeout_s, follow_redirects=False) as client:
            issued = (await client.get(f"{self.BASE}/2/files/issued", headers=headers)).json()
            code = DOC_TYPE_CODES.get(doc_type)
            item = next((i for i in issued.get("items", []) if i.get("doctype") == code), None)
            if not item:
                raise ProblemError(404, "Document not found in DigiLocker", "errors.not_found")
            xml = await client.get(f"{self.BASE}/1/xml/{item['uri']}", headers=headers)
            xml.raise_for_status()
            pdf = await client.get(f"{self.BASE}/1/file/{item['uri']}", headers=headers)
        # Issued XML carries structured fields; parsing per issuer schema happens in onboarding.
        return PulledDocument(doc_type, {"issuer_xml": xml.text[:20000]}, [], pdf.content, item.get("issuer", ""),
                              item["uri"], False)


def get_digilocker() -> DigiLockerAdapter:
    return RealDigiLocker() if get_settings().digilocker_mode == "real" else SandboxDigiLocker()
