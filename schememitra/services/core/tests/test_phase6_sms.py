"""Phase 6 (claims C13, C14): a phone with no data connection can still apply and track.

The codec is a twin of packages/contracts/src/sms-codec.ts and both are checked against the
same fixture, so a message composed on the phone always means the same thing on the server."""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.modules.eligibility.loader import invalidate_ruleset
from app.modules.notify import codec
from app.modules.notify.sms import CONSOLE_FEED, segments
from app.seed.partners import seed_partners
from app.seed.personas import PERSONAS
from app.seed.schemes import seed_schemes
from app.seed.users import seed_users

FIXTURE = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures" / "sms-cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))
INTERNAL = {"x-internal-secret": get_settings().internal_shared_secret}


@pytest.fixture(scope="module", autouse=True)
async def _seeded():  # type: ignore[no-untyped-def]
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await seed_schemes(session)
        await seed_partners(session)
        await seed_users(session)
        await session.commit()
    invalidate_ruleset()
    yield


@pytest.mark.parametrize("case", [c for c in CASES if c.get("facts")], ids=lambda c: c["name"])
def test_codec_matches_the_shared_fixture(case: dict) -> None:  # type: ignore[type-arg]
    assert codec.encode_apply(case["facts"], case["ref"]) == case["wire"]
    decoded = codec.decode(case["wire"])
    assert decoded.kind == "apply" and decoded.facts == case["decoded"]
    assert all(len(part) <= codec.PART_CHARS for part in case["wire"])
    assert len(case["wire"]) <= codec.MAX_PARTS


@pytest.mark.parametrize("case", [c for c in CASES if c.get("expect")], ids=lambda c: c["name"])
def test_codec_commands_and_rejections(case: dict) -> None:  # type: ignore[type-arg]
    decoded = codec.decode(case["wire"])
    assert decoded.kind == case["expect"]["kind"]
    if tid := case["expect"].get("tracking_id"):
        assert decoded.tracking_id == tid
    if reason := case["expect"].get("reason"):
        assert decoded.reason == reason


def test_one_application_fits_in_one_gsm7_message() -> None:
    wire = codec.encode_apply(CASES[0]["facts"], "A1")
    assert len(wire) == 1 and segments(wire[0]) == 1


async def test_sms_application_creates_a_draft_with_scheme_and_lender(client) -> None:  # type: ignore[no-untyped-def]
    savita = PERSONAS["savitaben"]
    facts = {
        "full_name": "Savitaben Rathwa", "age": 34, "gender": "female", "social_category": "sc", "state_code": "GJ",
        "district_code": "GJ-DAH", "pincode": "389151", "annual_family_income_rupees": 120_000, "education_level": "primary",
        "business_type": "dairy", "project_cost_rupees": 60_000, "loan_needed_rupees": 60_000, "shg_member": True,
        "existing_loans": False, "has_disability": False, "phone": savita.phone, "lang": "gu",
    }
    CONSOLE_FEED.clear()
    wire = codec.encode_apply(facts, "S1")
    res = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": savita.phone, "text": wire[0], "provider": "console"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["understood"] == "apply" and body["created"] is True
    tid = body["tracking_id"]
    assert tid.startswith("SM-GJ-")
    # The application itself is one GSM-7 segment; the Gujarati reply is UCS-2, so it costs two.
    assert segments(wire[0]) == 1
    assert tid in body["body"] and body["segments"] == 2

    track = (await client.get(f"/v1/track/{tid}")).json()
    assert track["status"] == "draft" and track["scheme_code"] == savita.expected_scheme
    assert track["partner_name"].startswith("Dahod District SCA")
    assert "Savitaben" not in str(track)  # public tracking carries no personal data

    # The reply is Gujarati, because the sender said so.
    assert CONSOLE_FEED and any("ક" <= ch <= "૿" for ch in CONSOLE_FEED[-1]["body"])


async def test_multipart_waits_for_every_part_and_rejects_corruption(client) -> None:  # type: ignore[no-untyped-def]
    facts = {"full_name": "A" * 200, "age": 30, "district_code": "RJ-BAR", "loan_needed_rupees": 100_000}
    wire = codec.encode_apply(facts, "M2")
    assert len(wire) > 1
    first = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000009", "text": wire[0]})
    assert first.json() == {**first.json(), "understood": "partial", "expected": len(wire), "received": [1]}
    for part in wire[1:-1]:
        await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000009", "text": part})
    last = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000009", "text": wire[-1]})
    assert last.json()["understood"] == "apply"

    broken = codec.encode_apply({"age": 44, "district_code": "RJ-BAR"}, "X9")[0][:-4] + "FFFF"
    res = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000008", "text": broken})
    assert res.json()["understood"] == "unknown" and res.json()["reason"] == "checksum"


async def test_status_lookup_and_help_over_sms(client) -> None:  # type: ignore[no-untyped-def]
    facts = {"full_name": "Ramesh Kanaram Meghwal", "age": 41, "gender": "male", "social_category": "sc",
             "state_code": "RJ", "district_code": "RJ-BAR", "annual_family_income_rupees": 180_000,
             "business_type": "tailoring", "project_cost_rupees": 450_000, "loan_needed_rupees": 400_000,
             "phone": PERSONAS["ramesh"].phone, "lang": "hi"}
    created = await client.post("/v1/sms/inbound", headers=INTERNAL,
                                json={"from": PERSONAS["ramesh"].phone, "text": codec.encode_apply(facts, "R1")[0]})
    tid = created.json()["tracking_id"]

    CONSOLE_FEED.clear()
    status = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": PERSONAS["ramesh"].phone, "text": f"STATUS {tid.lower()}"})
    assert status.json()["understood"] == "status" and status.json()["found"] is True
    assert tid in status.json()["body"] and "आवेदन" in CONSOLE_FEED[-1]["body"] or "SchemeMitra" in CONSOLE_FEED[-1]["body"]

    missing = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000007", "text": "STATUS SM-GJ-26-AAAAAAA"})
    assert missing.json()["understood"] == "status" and missing.json()["found"] is False

    helped = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000007", "text": "help"})
    assert helped.json()["understood"] == "help" and "STATUS" in helped.json()["body"]


async def test_sms_endpoints_are_internal_only(client) -> None:  # type: ignore[no-untyped-def]
    assert (await client.post("/v1/sms/inbound", json={"from": "9000000007", "text": "help"})).status_code == 403
    assert (await client.post("/v1/ivr/next", json={"lang": "hi"})).status_code == 403


async def test_ivr_reads_the_status_out_loud(client) -> None:  # type: ignore[no-untyped-def]
    facts = {"age": 34, "gender": "female", "social_category": "sc", "district_code": "GJ-DAH",
             "annual_family_income_rupees": 120_000, "business_type": "dairy", "project_cost_rupees": 60_000,
             "loan_needed_rupees": 60_000, "lang": "gu"}
    created = await client.post("/v1/sms/inbound", headers=INTERNAL, json={"from": "9000000001", "text": codec.encode_apply(facts, "I1")[0]})
    tid = created.json()["tracking_id"]

    greeting = (await client.post("/v1/ivr/next", headers=INTERNAL, json={"lang": "hi"})).json()
    assert greeting["expect"] == "tracking_id" and greeting["say"]
    spoken = (await client.post("/v1/ivr/next", headers=INTERNAL, json={"tracking_id": tid, "lang": "gu"})).json()
    assert spoken["expect"] == "end" and tid in spoken["say"] and spoken["status"] == "draft"
    unknown = (await client.post("/v1/ivr/next", headers=INTERNAL, json={"tracking_id": "SM-GJ-26-AAAAAAA", "lang": "hi"})).json()
    assert unknown["expect"] == "tracking_id"
