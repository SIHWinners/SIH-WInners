from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.eligibility.engine import evaluate_scheme
from app.modules.eligibility.loader import RuleSet, SchemeRules, get_ruleset
from app.modules.eligibility.schemas import ApplicantFacts


def build_offer(rules: SchemeRules, facts: dict[str, Any]) -> dict[str, Any]:
    d = rules.doc
    max_loan = d["loan_limits"]["max_paise"]
    wanted = facts.get("loan_needed_paise")
    if wanted is None and facts.get("project_cost_paise") is not None:
        # Without an explicit ask, suggest the apex share of the project cost.
        wanted = facts["project_cost_paise"] * d["funding_pattern"]["apex_bps"] // 10000
    principal = min(wanted, max_loan) if wanted is not None else None
    return {
        "rate_bps": rules.rate_bps_for(principal or 0, facts.get("gender")),
        "max_loan_paise": max_loan,
        "suggested_principal_paise": principal,
        "default_tenure_months": d["repayment"]["default_tenure_months"],
        "max_tenure_months": d["repayment"]["max_tenure_months"],
        "moratorium_default_months": d["moratorium"]["default_months"],
        "moratorium_max_months": d["moratorium"]["max_months"],
        "moratorium_treatment": d["moratorium"]["treatment"],
        "repayment_frequency": d["repayment"]["frequency"],
        "funding_pattern": d["funding_pattern"],
        "processing_days": d.get("processing_days", 30),
    }


def evaluate_against(ruleset: RuleSet, applicant: ApplicantFacts, codes: list[str] | None = None) -> dict[str, Any]:
    facts = applicant.facts()
    results = []
    for code, rules in sorted(ruleset.schemes.items()):
        if codes and code not in codes:
            continue
        outcome = evaluate_scheme(rules.conditions, facts, rules.params)
        d = rules.doc
        results.append({
            "code": code, "name": d["name"], "apex_corp": d["apex_corp"], "loan_type": d["loan_type"],
            "version": rules.version, "rule_version_id": rules.rule_version_id, "source_url": d["source_url"],
            "verified_on": d.get("verified_on"), "needs_verification": d["needs_verification"],
            "documents_required": d["documents_required"], "channel_partner_types": d["channel_partner_types"],
            "offer": build_offer(rules, facts), **outcome,
        })

    eligible = [r for r in results if r["status"] == "eligible"]
    # Deterministic default order: cheapest money first. The ranking module re-orders
    # eligible schemes with the ML model and explains why; it never adds or removes any.
    eligible.sort(key=lambda r: (r["offer"]["rate_bps"], -r["offer"]["funding_pattern"]["apex_bps"], r["code"]))
    near = [r for r in results if r["status"] == "ineligible" and r["near_miss"] is not None]
    return {
        "rules_etag": ruleset.bundle()["etag"],
        "eligible": [r["code"] for r in eligible],
        "ineligible": [r["code"] for r in results if r["status"] == "ineligible"],
        "needs_info": [r["code"] for r in results if r["status"] == "needs_info"],
        "near_misses": [r["code"] for r in near],
        "next_best": eligible[0]["code"] if eligible else None,
        "results": results,
    }


async def evaluate(session: AsyncSession, applicant: ApplicantFacts, codes: list[str] | None = None) -> dict[str, Any]:
    """Rules decide who is eligible; the ranker then only re-orders that eligible list (C1)."""
    from app.modules.ranking.service import RADIUS_KM, rank
    from app.modules.routing.service import nearby

    out = evaluate_against(await get_ruleset(session), applicant, codes)
    facts = applicant.facts()
    by_code = {r["code"]: r for r in out["results"]}
    eligible = [by_code[c] for c in out["eligible"]]
    nearby_by_code: dict[str, dict[str, Any] | None] = {}
    for r in eligible:
        if facts.get("lat") is not None and facts.get("lng") is not None:
            nearby_by_code[r["code"]] = await nearby(
                session, lat=facts["lat"], lng=facts["lng"], scheme=r["code"], category=facts.get("social_category"),
                radius_km=RADIUS_KM, loan_paise=facts.get("loan_needed_paise"), limit=10)
        else:
            nearby_by_code[r["code"]] = None
    ranked, method = await rank(eligible, facts, nearby_by_code)
    for r in ranked:
        by_code[r["code"]]["rank"] = r["rank"]
    out["eligible"] = [r["code"] for r in ranked]
    out["next_best"] = out["eligible"][0] if ranked else None
    out["ranking_method"] = method
    return out
