"""Phase 3 gate (API level): Ramesh from draft to submitted file, with document checks,
DigiLocker fallback, name matching, readiness, consent, signed QR, loan file and tracking."""

import pytest
from pypdf import PdfReader

from app.core.ids import is_valid_tracking_id
from app.modules.applications.qr import verify_qr
from app.modules.documents.aadhaar import is_valid_aadhaar, verhoeff_digit
from app.modules.documents.names import match_names
from app.modules.documents.ocr import DEMO_DOCS_DIR
from app.modules.eligibility.loader import invalidate_ruleset
from app.modules.notify.sms import CONSOLE_FEED, segments
from app.seed.demo_documents import seed_demo_documents
from app.seed.partners import seed_partners
from app.seed.personas import PERSONAS
from app.seed.schemes import seed_schemes
from tests.conftest import login


@pytest.fixture(scope="module", autouse=True)
async def _seeded():  # type: ignore[no-untyped-def]
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await seed_schemes(session)
        await seed_partners(session)
        await seed_demo_documents(session)
        await session.commit()
    invalidate_ruleset()
    yield


def test_aadhaar_verhoeff() -> None:
    base = "45391876204"
    assert is_valid_aadhaar(base + verhoeff_digit(base))
    assert not is_valid_aadhaar(base + str((int(verhoeff_digit(base)) + 1) % 10))
    assert not is_valid_aadhaar("0123 4567 8901")


def test_name_variations() -> None:
    r = match_names("Shri Ramesh S/O Late Kanaram", "RAMESH KANARAM MEGHWAL")
    assert r.matched and "honorific_removed" in r.reasons and "relation_removed" in r.reasons and "anchor_father" in r.reasons
    no_anchor = match_names("Ramesh Meghwal", "Meghwal Ramesh")
    assert not no_anchor.matched and "no_anchor" in no_anchor.reasons and "token_order" in no_anchor.reasons
    assert match_names("रमेश कानाराम मेघवाल", "Ramesh Kanaram Meghwal", dob_left="1985-07-02", dob_right="1985-07-02").matched


def test_sms_segments() -> None:
    assert segments("a" * 160) == 1 and segments("a" * 161) == 2
    assert segments("नमस्ते" * 12) == 2  # UCS-2: 72 code units > 70


async def _partner_id(client, persona: str, scheme: str) -> str:  # type: ignore[no-untyped-def]
    lat, lng = PERSONAS[persona].location
    body = (await client.get("/v1/partners/nearby", params={"lat": lat, "lng": lng, "scheme": scheme,
                                                             "category": PERSONAS[persona].facts["social_category"]})).json()
    return body["partners"][0]["id"]


async def _upload(client, headers, app_id: str, persona: str, doc_type: str):  # type: ignore[no-untyped-def]
    data = (DEMO_DOCS_DIR / persona / f"{doc_type}.png").read_bytes()
    res = await client.post("/v1/documents", headers=headers, data={"application_id": app_id, "doc_type": doc_type, "source": "camera"},
                            files={"file": (f"{doc_type}.png", data, "image/png")})
    assert res.status_code == 200, res.text
    return res.json()


async def test_ramesh_end_to_end(client) -> None:  # type: ignore[no-untyped-def]
    ramesh = PERSONAS["ramesh"]
    headers = await login(client, ramesh.phone)
    partner_id = await _partner_id(client, "ramesh", "NSFDC_TERM_LOAN")
    draft = {
        "client_uuid": "test-ramesh-0001", "lang": "hi",
        "personal": {"full_name": "Ramesh Kanaram Meghwal", "father_name": "Kanaram", "dob": "1985-07-02", "phone": ramesh.phone},
        "facts": {**ramesh.facts, "lat": ramesh.location[0], "lng": ramesh.location[1]},
        "scheme_code": "NSFDC_TERM_LOAN",
        "plan": {"principal_paise": 400_000_00, "rate_bps": 800, "tenure_months": 84, "moratorium_months": 6},
        "partner_id": partner_id,
    }
    created = await client.post("/v1/applications", json=draft, headers=headers)
    assert created.status_code == 200, created.text
    app = created.json()
    assert is_valid_tracking_id(app["tracking_id"]) and app["tracking_id"].startswith("SM-RJ-")
    assert app["eligibility_status"] == "eligible" and app["finance"]["emi_paise"] > 0
    replay = (await client.post("/v1/applications", json=draft, headers=headers)).json()
    assert replay["id"] == app["id"]  # idempotent on client_uuid

    # someone else cannot see it
    other = await login(client, "9000000001")
    assert (await client.get(f"/v1/applications/{app['id']}", headers=other)).status_code == 404

    # submit is blocked until the file is ready (C16)
    early = await client.post(f"/v1/applications/{app['id']}/submit", headers=headers)
    assert early.status_code == 422 and early.json()["user_message_key"] in ("send.not_ready", "send.consent_title")

    aadhaar = await _upload(client, headers, app["id"], "ramesh", "aadhaar")
    assert aadhaar["status"] == "ok" and "aadhaar_last4" in aadhaar["fields"] and "aadhaar_hash" not in aadhaar["fields"]
    faded = await _upload(client, headers, app["id"], "ramesh", "caste_certificate")
    assert faded["status"] == "retake" and faded["suggest_digilocker"] is True  # C10 trigger

    token = (await client.post("/v1/documents/digilocker/consent", json={"code": "sandbox"}, headers=headers)).json()["consent_token"]
    pulled = await client.post("/v1/documents/digilocker/pull", headers=headers,
                               json={"application_id": app["id"], "doc_type": "caste_certificate", "consent_token": token})
    assert pulled.status_code == 200, pulled.text
    assert pulled.json()["verified"] is True and pulled.json()["source"] == "digilocker"

    for doc_type in ("income_certificate", "bank_passbook", "project_quotation"):
        assert (await _upload(client, headers, app["id"], "ramesh", doc_type))["status"] == "ok"

    ready = (await client.post(f"/v1/applications/{app['id']}/readiness", headers=headers)).json()
    assert ready["ready"] is True and ready["score"] >= 90, ready
    caste = ready["name_matches"]["caste_certificate"]
    assert caste["matched"] and "relation_removed" in caste["reasons"]  # C11 on the real document path

    consent = await client.post(f"/v1/applications/{app['id']}/consent", headers=headers,
                                json={"method": "otp", "language": "hi", "evidence": {"otp_verified": True}})
    assert consent.status_code == 200
    CONSOLE_FEED.clear()
    submitted = await client.post(f"/v1/applications/{app['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    claims = verify_qr(result["qr_token"])  # C9: signed, no PII
    assert claims["tid"] == app["tracking_id"] and set(claims) == {"tid", "h", "pid", "iat", "exp"}
    assert CONSOLE_FEED and app["tracking_id"] in CONSOLE_FEED[0]["body"]  # SMS in Hindi with tracking ID
    assert "आवेदन" in CONSOLE_FEED[0]["body"]

    pdf = await client.get(f"/v1/applications/{app['id']}/loan-file.pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert len(pdf.content) < 400_000  # C18 size budget
    import io

    text = "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert app["tracking_id"] in text and "free" in text.lower()

    track = (await client.get(f"/v1/track/{app['tracking_id'].lower()}")).json()
    assert track["status"] == "submitted" and track["partner_name"].startswith("Barmer District SCA")
    assert "Ramesh" not in str(track)  # tracking is public: no personal data
    typo = app["tracking_id"][:-1] + ("A" if app["tracking_id"][-1] != "A" else "B")
    assert (await client.get(f"/v1/track/{typo}")).status_code == 422

    locked = await client.post("/v1/documents", headers=headers, data={"application_id": app["id"], "doc_type": "aadhaar"},
                               files={"file": ("a.png", (DEMO_DOCS_DIR / "ramesh" / "aadhaar.png").read_bytes(), "image/png")})
    assert locked.status_code == 409


async def test_upload_hardening_and_erasure(client) -> None:  # type: ignore[no-untyped-def]
    edge = PERSONAS["edge"]
    headers = await login(client, edge.phone)
    partner_id = await _partner_id(client, "edge", "MUDRA_KISHOR_BANK")
    app = (await client.post("/v1/applications", headers=headers, json={
        "client_uuid": "test-edge-0001", "personal": {"full_name": edge.full_name, "phone": edge.phone},
        "facts": {**edge.facts, "lat": edge.location[0], "lng": edge.location[1]}, "scheme_code": "MUDRA_KISHOR_BANK",
        "plan": {"principal_paise": 300_000_00, "rate_bps": 1150, "tenure_months": 48}, "partner_id": partner_id,
    })).json()
    bad = await client.post("/v1/documents", headers=headers, data={"application_id": app["id"], "doc_type": "aadhaar"},
                            files={"file": ("x.png", b"<script>alert(1)</script>", "image/png")})
    assert bad.status_code == 415 and bad.json()["user_message_key"] == "errors.unsupported_file"
    doc = await _upload(client, headers, app["id"], "edge", "bank_passbook")
    image = await client.get(f"/v1/documents/{doc['document_id']}/image", headers=headers)
    assert image.status_code == 200 and image.content[:3] == b"\xff\xd8\xff"  # re-encoded JPEG, EXIF stripped

    erased = await client.post(f"/v1/applications/{app['id']}/erase", headers=headers)
    assert erased.json() == {"erased": True}
    assert (await client.get(f"/v1/applications/{app['id']}", headers=headers)).status_code == 404
    assert (await client.get(f"/v1/track/{app['tracking_id']}")).status_code == 404
