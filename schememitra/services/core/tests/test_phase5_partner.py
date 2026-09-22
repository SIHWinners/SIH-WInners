"""Phase 5 gate (API level): ML ranking only re-orders eligible schemes and explains itself
truthfully; the partner scans the signed QR, reviews and decides; only the lender can decide
(C21); every decision updates the citizen's timeline and sends an SMS in their language."""

import time

import pytest
from pypdf import PdfReader

from app.core import events
from app.core.i18n import catalogue
from app.core.resilience import set_chaos
from app.modules.applications.status import can_transition
from app.modules.documents.ocr import DEMO_DOCS_DIR
from app.modules.eligibility.loader import get_ruleset, invalidate_ruleset
from app.modules.eligibility.schemas import ApplicantFacts
from app.modules.eligibility.service import evaluate, evaluate_against
from app.modules.notify.sms import CONSOLE_FEED
from app.modules.ranking import service as ranking
from app.seed.demo_documents import seed_demo_documents
from app.seed.partners import seed_partners
from app.seed.personas import PERSONAS
from app.seed.schemes import seed_schemes
from app.seed.users import seed_users
from tests.conftest import login

DAHOD_OFFICER, BARMER_OFFICER, ADMIN = "9000000020", "9000000021", "9000000030"


@pytest.fixture(scope="module", autouse=True)
async def _seeded():  # type: ignore[no-untyped-def]
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await seed_schemes(session)
        await seed_partners(session)
        await seed_users(session)
        await seed_demo_documents(session)
        await session.commit()
    invalidate_ruleset()
    yield


def _lookup(key: str) -> str | None:
    node: object = catalogue("en")
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


@pytest.mark.parametrize("persona", ["savitaben", "ramesh", "kavya", "imran"])
async def test_ranking_puts_the_intended_scheme_first_and_explains_truthfully(persona: str) -> None:
    from app.db.session import get_sessionmaker

    p = PERSONAS[persona]
    lat, lng = p.location
    facts = ApplicantFacts(**p.facts, lat=lat, lng=lng)
    async with get_sessionmaker()() as session:
        ranked = await evaluate(session, facts)
        rules_only = evaluate_against(await get_ruleset(session), facts)
    assert ranked["ranking_method"] == "model" and ranking.model_loaded()
    assert set(ranked["eligible"]) == set(rules_only["eligible"])  # ML never adds or removes a scheme
    assert ranked["eligible"][0] == p.expected_scheme == ranked["next_best"]
    by_code = {r["code"]: r for r in ranked["results"]}
    for position, code in enumerate(ranked["eligible"], start=1):
        rank = by_code[code]["rank"]
        assert rank["position"] == position
        for reason in rank["reasons"]:
            assert _lookup(reason["key"]) is not None, reason["key"]
            assert ranking.TRUE_WHEN[reason["feature"]](rank["features"]), (code, reason)


async def test_ranking_falls_back_to_heuristic_and_endpoint_works(client) -> None:  # type: ignore[no-untyped-def]
    p = PERSONAS["savitaben"]
    lat, lng = p.location
    body = {"applicant": {**p.facts, "lat": lat, "lng": lng}}
    set_chaos("ranking_model", True)
    try:
        res = await client.post("/v1/ranking/rank", json=body)
        assert res.status_code == 200 and res.json()["method"] == "heuristic"
        assert [r["position"] for r in res.json()["ranked"]] == list(range(1, len(res.json()["ranked"]) + 1))
    finally:
        set_chaos("ranking_model", False)
    res = await client.post("/v1/ranking/rank", json=body)
    assert res.json()["method"] == "model" and res.json()["ranked"][0]["code"] == p.expected_scheme


def test_only_lenders_decide() -> None:
    for target in ("sanctioned", "rejected"):
        assert can_transition("under_review", target, "partner_officer")
        assert not can_transition("under_review", target, "admin")
        assert not can_transition("under_review", target, "csc_operator")
        assert not can_transition("under_review", target, "citizen")
    assert not can_transition("sanctioned", "disbursed", "admin")


async def _submitted_savitaben(client, headers) -> dict:  # type: ignore[no-untyped-def,type-arg]
    """Savitaben's file, sent to the lender the Dahod demo officer works for."""
    p = PERSONAS["savitaben"]
    lat, lng = p.location
    officer = await login(client, DAHOD_OFFICER)
    dahod = {"id": (await client.get("/v1/auth/me", headers=officer)).json()["partner_id"]}
    draft = {"client_uuid": f"test-savita-partner-{time.time_ns()}", "lang": "gu",
             "personal": {"full_name": "Savitaben Rathwa", "father_name": "Ramsinh Rathwa", "dob": "1992-03-14", "phone": p.phone},
             "facts": {**p.facts, "lat": lat, "lng": lng}, "scheme_code": p.expected_scheme,
             "plan": {"principal_paise": 60_000_00, "rate_bps": 500, "tenure_months": 36, "moratorium_months": 3},
             "partner_id": dahod["id"]}
    app = (await client.post("/v1/applications", json=draft, headers=headers)).json()
    for doc_type in ("aadhaar", "caste_certificate", "income_certificate", "bank_passbook"):
        data = (DEMO_DOCS_DIR / "savitaben" / f"{doc_type}.png").read_bytes()
        up = await client.post("/v1/documents", headers=headers, data={"application_id": app["id"], "doc_type": doc_type, "source": "camera"},
                               files={"file": (f"{doc_type}.png", data, "image/png")})
        assert up.status_code == 200, up.text
    consent = await client.post(f"/v1/applications/{app['id']}/consent", headers=headers, json={
        "method": "voice", "language": "gu",
        "evidence": {"otp_verified": True, "readback_text": "…", "voice_confirmation": "હા, બરાબર છે.", "transcript_engine": "sandbox",
                     "audio_base64": "never kept"}})
    assert consent.status_code == 200
    submitted = await client.post(f"/v1/applications/{app['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    return {**app, **submitted.json()}


async def test_partner_scan_review_and_decisions(client, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    published: list[tuple[str, str, dict]] = []  # type: ignore[type-arg]
    original = events.publish

    def capture(channel, event, data, session=None):  # type: ignore[no-untyped-def]
        if session is None:
            published.append((channel, event, data))
        original(channel, event, data, session)

    monkeypatch.setattr(events, "publish", capture)
    citizen = await login(client, PERSONAS["savitaben"].phone)
    app = await _submitted_savitaben(client, citizen)
    tid, app_id = app["tracking_id"], app["id"]
    assert (f"track:{tid}", "status", {"tracking_id": tid, "status": "submitted", "template": "sms.submitted"}) in published

    officer = await login(client, DAHOD_OFFICER)
    other = await login(client, BARMER_OFFICER)
    admin = await login(client, ADMIN)

    queue = (await client.get("/v1/partner/queue", params={"group": "new"}, headers=officer)).json()
    assert any(i["tracking_id"] == tid and i["applicant_name"] == "Savitaben Rathwa" for i in queue["items"])
    assert queue["partner_name"].startswith("Dahod District SCA")
    assert not any(i["tracking_id"] == tid for i in (await client.get("/v1/partner/queue", headers=other)).json()["items"])
    assert (await client.get("/v1/partner/queue", headers=citizen)).status_code == 403

    # Scan: the wrong lender cannot open it; a forged token fails; the right lender receives it.
    assert (await client.post("/v1/partner/scan", json={"jws": app["qr_token"]}, headers=other)).status_code == 403
    forged = app["qr_token"][:-4] + ("AAAA" if not app["qr_token"].endswith("AAAA") else "BBBB")
    bad = await client.post("/v1/partner/scan", json={"jws": forged}, headers=officer)
    assert bad.status_code == 400 and bad.json()["user_message_key"] == "errors.qr_invalid"
    scan = (await client.post("/v1/partner/scan", json={"jws": app["qr_token"]}, headers=officer)).json()
    assert scan == {**scan, "application_id": app_id, "status": "received_by_partner", "signature_valid": True,
                    "file_unchanged": True, "received_now": True}

    review = (await client.get(f"/v1/partner/applications/{app_id}", headers=officer)).json()
    assert review["allowed_actions"] == ["start_review", "request_documents", "reject"]
    assert {d["type"] for d in review["documents"]} >= {"aadhaar", "caste_certificate", "income_certificate", "bank_passbook"}
    assert review["consent"]["method"] == "voice" and review["consent"]["evidence"]["voice_confirmation"] == "હા, બરાબર છે."
    assert "audio_base64" not in review["consent"]["evidence"]  # text evidence only
    assert review["integrity"]["unchanged_since_submit"] is True
    actions = [a["action"] for a in review["audit"]]
    assert actions[0] == "application.created"
    assert actions.index("consent.granted") < actions.index("application.submitted") < actions.index("application.received_by_partner")
    assert (await client.get(f"/v1/partner/applications/{app_id}", headers=other)).status_code == 404

    async def decide(headers, body):  # type: ignore[no-untyped-def]
        return await client.post(f"/v1/partner/applications/{app_id}/decision", json=body, headers=headers)

    assert (await decide(officer, {"action": "request_documents"})).status_code == 422
    CONSOLE_FEED.clear()
    started = time.perf_counter()
    asked = await decide(officer, {"action": "request_documents", "documents": ["shg_certificate"], "note": "SHG letter please"})
    assert asked.status_code == 200, asked.text
    assert time.perf_counter() - started < 2.0  # Phase 5 gate: decision → timeline + SMS within 2 s
    assert CONSOLE_FEED and tid in CONSOLE_FEED[0]["body"] and "SHG" in CONSOLE_FEED[0]["body"]
    track = (await client.get(f"/v1/track/{tid}")).json()
    assert track["status"] == "documents_requested" and track["requested_documents"] == ["shg_certificate"]
    assert (f"track:{tid}", "status", {"tracking_id": tid, "status": "documents_requested", "template": "sms.documents_requested"}) in published

    data = (DEMO_DOCS_DIR / "savitaben" / "shg_certificate.png").read_bytes()
    await client.post("/v1/documents", headers=citizen, data={"application_id": app_id, "doc_type": "shg_certificate", "source": "camera"},
                      files={"file": ("shg.png", data, "image/png")})
    assert (await client.post(f"/v1/applications/{app_id}/resubmit", headers=citizen)).status_code == 200
    assert (await decide(officer, {"action": "start_review"})).json()["application"]["status"] == "under_review"

    # C21: an admin cannot sanction, nor can the citizen; the lender can.
    no = await decide(admin, {"action": "approve"})
    assert no.status_code == 403 and no.json()["user_message_key"] == "officer.lender_only"
    assert (await decide(citizen, {"action": "approve"})).status_code == 403
    CONSOLE_FEED.clear()
    approved = await decide(officer, {"action": "approve", "note": "Visit branch on Monday",
                                      "sanction": {"amount_paise": 55_000_00, "rate_bps": 500, "tenure_months": 36, "moratorium_months": 3}})
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["application"]["status"] == "sanctioned" and body["finance"]["sanction"]["amount_paise"] == 55_000_00
    assert body["allowed_actions"] == ["disburse"] and body["sanction_letter_url"]
    assert CONSOLE_FEED and "Dahod District SCA" in CONSOLE_FEED[0]["body"]

    letter = await client.get(f"/v1/applications/{app_id}/sanction-letter.pdf", headers=citizen)
    assert letter.status_code == 200 and letter.headers["content-type"] == "application/pdf"
    import io

    text = "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(letter.content)).pages)
    assert tid in text and "55,000" in text and "Demo lender" in text
    assert (await client.get(f"/v1/applications/{app_id}/sanction-letter.pdf", headers=other)).status_code == 404

    assert (await decide(officer, {"action": "disburse"})).json()["application"]["status"] == "disbursed"
    assert (await decide(officer, {"action": "reject", "reason_code": "other"})).status_code == 409
    timeline = [e["status"] for e in (await client.get(f"/v1/track/{tid}")).json()["timeline"]]
    assert timeline[-3:] == ["under_review", "sanctioned", "disbursed"]


async def test_reject_needs_a_coded_reason(client) -> None:  # type: ignore[no-untyped-def]
    citizen = await login(client, PERSONAS["savitaben"].phone)
    app = await _submitted_savitaben(client, citizen)
    officer = await login(client, DAHOD_OFFICER)
    path = f"/v1/partner/applications/{app['id']}/decision"
    received = await client.post(path, json={"action": "receive"}, headers=officer)
    assert received.status_code == 200, received.text
    assert (await client.post(path, json={"action": "reject", "reason_code": "because"}, headers=officer)).status_code == 422
    CONSOLE_FEED.clear()
    res = await client.post(path, json={"action": "reject", "reason_code": "income_proof_invalid"}, headers=officer)
    assert res.status_code == 200 and res.json()["application"]["rejection_reason_code"] == "income_proof_invalid"
    assert CONSOLE_FEED and "Not approved" not in CONSOLE_FEED[0]["body"]  # Gujarati SMS, not English
