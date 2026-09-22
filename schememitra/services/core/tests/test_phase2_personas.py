"""Phase 2 gate: personas 2 (Ramesh) and 5 (edge) get correct eligibility, EMI and partners."""

import pytest

from app.modules.eligibility.loader import invalidate_ruleset, load_rule_files
from app.modules.routing.geo import geohash, haversine_km
from app.modules.routing.health import Metrics, exclusion_reason, health_score, rank_score
from app.seed.partners import seed_partners
from app.seed.personas import PERSONAS
from app.seed.schemes import seed_schemes


@pytest.fixture(scope="module", autouse=True)
async def _seeded():  # type: ignore[no-untyped-def]
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await seed_schemes(session)
        await seed_partners(session)
        await session.commit()
    invalidate_ruleset()
    yield


def test_all_rule_files_validate_and_carry_sources() -> None:
    docs = load_rule_files()
    assert 8 <= len(docs) <= 12
    for doc in docs:
        assert doc["source_url"].startswith("https://") and doc["verified_on"]
    assert {d["loan_type"] for d in docs} >= {"micro_finance", "term_loan", "education_loan", "group_loan", "women_scheme"}
    assert {d["apex_corp"] for d in docs} >= {"NSFDC", "NBCFDC", "NSKFDC", "NDFDC"}


async def evaluate(client, persona: str) -> dict:  # type: ignore[no-untyped-def]
    res = await client.post("/v1/eligibility/evaluate", json={"applicant": PERSONAS[persona].facts})
    assert res.status_code == 200, res.text
    return res.json()


async def test_ramesh_term_loan_with_rule_trace(client) -> None:  # type: ignore[no-untyped-def]
    body = await evaluate(client, "ramesh")
    assert "NSFDC_TERM_LOAN" in body["eligible"]
    assert "NBCFDC_INDIVIDUAL_LOAN" in body["ineligible"]  # OBC-only scheme
    term = next(r for r in body["results"] if r["code"] == "NSFDC_TERM_LOAN")
    income = next(row for row in term["trace"] if row["id"] == "income")
    # C8: "Your family income ₹1,80,000 is within the ₹5,00,000 limit ✓"
    assert income["result"] == "pass" and income["sentence"]["key"] == "rules.c.income_within"
    assert income["sentence"]["params"]["value"]["value"] == 180_000_00
    assert income["sentence"]["params"]["limit"]["value"] == 500_000_00
    assert term["offer"]["rate_bps"] == 800 and term["offer"]["funding_pattern"]["apex_bps"] == 9000


async def test_ramesh_emi(client) -> None:  # type: ignore[no-untyped-def]
    res = (await client.post("/v1/finance/emi", json={
        "principal_paise": 400_000_00, "rate_bps": 800, "tenure_months": 60, "moratorium_months": 6,
        "project_cost_paise": 450_000_00, "split": {"apex_bps": 9000, "partner_bps": 500, "beneficiary_bps": 500},
        "monthly_income_paise": 15_000_00, "max_tenure_months": 84,
    })).json()
    assert 8_200_00 < res["emi_paise"] < 8_500_00
    assert res["split_breakdown"] == {"project_cost_paise": 450_000_00, "apex_paise": 405_000_00, "partner_paise": 22_500_00,
                                      "beneficiary_paise": 22_500_00, "apex_bps": 9000, "partner_bps": 500,
                                      "beneficiary_bps": 500}
    assert res["affordability"]["affordable"] is False  # ₹8.3k > 40% of ₹15k
    assert res["affordability"]["suggest_principal_paise"] is not None


async def test_ramesh_partners_skip_weak_recovery_bank(client) -> None:  # type: ignore[no-untyped-def]
    lat, lng = PERSONAS["ramesh"].location
    res = await client.get("/v1/partners/nearby", params={"lat": lat, "lng": lng, "scheme": "NSFDC_TERM_LOAN",
                                                          "category": "sc", "radius_km": 40, "loan_paise": 400_000_00})
    body = res.json()
    assert body["partners"], body
    assert body["partners"][0]["name"].startswith("Barmer District SCA")
    skipped = {e["name"]: e["reason"] for e in body["excluded"]}
    weak = next(name for name in skipped if name.startswith("Janseva National Bank — Barmer"))
    assert skipped[weak] == "low_recovery"
    nearest_overall = min([*body["partners"], *body["excluded"]], key=lambda p: p["distance_km"])
    assert nearest_overall["name"] == weak  # C4: the closest lender is the one we skip
    again = (await client.get("/v1/partners/nearby", params={"lat": lat, "lng": lng, "scheme": "NSFDC_TERM_LOAN",
                                                             "category": "sc", "radius_km": 40,
                                                             "loan_paise": 400_000_00})).json()
    assert again["cache"] == "hit"


async def test_edge_persona_near_miss_and_next_best(client) -> None:  # type: ignore[no-untyped-def]
    body = await evaluate(client, "edge")
    term = next(r for r in body["results"] if r["code"] == "NSFDC_TERM_LOAN")
    assert term["status"] == "ineligible" and term["failed"] == ["income"]
    assert term["near_miss"]["change"] == {"key": "rules.change.income_below",
                                           "params": {"limit": {"type": "money", "value": 500_000_00}}}
    assert "NSFDC_TERM_LOAN" in body["near_misses"]
    assert body["next_best"] == "MUDRA_KISHOR_BANK"


async def test_other_personas_match_their_scheme(client) -> None:  # type: ignore[no-untyped-def]
    for key in ("savitaben", "kavya", "imran"):
        body = await evaluate(client, key)
        assert PERSONAS[key].expected_scheme in body["eligible"], (key, body["eligible"])
    sav = await evaluate(client, "savitaben")
    mahila = next(r for r in sav["results"] if r["code"] == "NSFDC_MAHILA_SAMRIDHI")
    assert mahila["near_miss"]["id"] == "loan_amount"  # ₹60,000 asked, ₹50,000 limit


async def test_rules_bundle_etag(client) -> None:  # type: ignore[no-untyped-def]
    first = await client.get("/v1/rules/bundle")
    etag = first.headers["etag"]
    assert len(first.json()["schemes"]) == len(load_rule_files())
    assert (await client.get("/v1/rules/bundle", headers={"if-none-match": etag})).status_code == 304


async def test_pincode_lookup(client) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/v1/geo/pincode/344001")).json()["name"] == "Barmer"
    assert (await client.get("/v1/geo/pincode/999999")).status_code == 404


def test_health_score_and_geo_helpers() -> None:
    strong = Metrics(0.95, 2.0, 14, 100, 40, 10)
    weak = Metrics(0.62, 15.0, 60, 100, 99, 140)
    assert health_score(strong)[0] > 80 > health_score(weak)[0]
    assert exclusion_reason(weak, 0.70, None) == "low_recovery"
    assert exclusion_reason(Metrics(0.9, 2, 14, 100, 100, 1), 0.70, None) == "capacity_exhausted"
    assert exclusion_reason(Metrics(0.9, 2, 14, 100, 50, 1), 0.70, 60) == "capacity_exhausted"
    assert rank_score(100, 0) == 1.0 and rank_score(100, 15) < 0.37
    assert geohash(25.7521, 71.3967) == geohash(25.7522, 71.3968)
    assert abs(haversine_km(20.0, 75.0, 21.0, 75.0) - 111.19) < 0.05  # one degree of latitude
