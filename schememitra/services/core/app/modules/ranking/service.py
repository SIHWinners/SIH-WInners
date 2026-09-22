"""Scheme ranking (spec §9.4, claim C1): ML orders, never decides.

Only schemes the rule engine already found eligible are ranked; nothing is added or removed.
The XGBoost LambdaMART model scores each option and TreeSHAP contributions become the
plain-language reasons. If the model file is missing, fails to load, or the admin chaos
toggle `xgboost` is on, the weighted heuristic serves the same list (§13)."""

import json
from functools import cache
from typing import Any

import numpy as np

from app.config import get_settings
from app.core.resilience import guarded
from app.logging import get_logger
from app.modules.finance.calc import emi_paise, instalments_for
from app.modules.ranking.features import FEATURES, REFERENCE_RATE_BPS, FeatureRow, doc_readiness
from app.modules.ranking.heuristic import BASELINE, heuristic_contributions

log = get_logger("ranking")
RADIUS_KM = 25.0


@cache
def _schema() -> dict[str, Any]:
    path = get_settings().ranking_model_path.parent / "feature_schema.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"features": [], "hist_sanction_prior_by_loan_type": {}}


@cache
def _booster() -> Any:
    import xgboost as xgb

    path = get_settings().ranking_model_path
    if not path.exists():
        raise FileNotFoundError("ranker model not trained (run ml/train.py)")
    booster = xgb.Booster()
    booster.load_model(path)
    return booster


def model_loaded() -> bool:
    return _booster.cache_info().currsize > 0


def warm() -> None:
    try:
        _booster()
    except Exception as err:  # noqa: BLE001 - the heuristic serves until a model exists
        log.warning("ranker model unavailable (%s); heuristic scorer in use", type(err).__name__)


def features_for(result: dict[str, Any], facts: dict[str, Any], nearby: dict[str, Any] | None,
                 uploaded: set[str] | None = None) -> tuple[FeatureRow, dict[str, Any]]:
    offer = result["offer"]
    limit = max(int(offer["max_loan_paise"]), 1)
    requested = facts.get("loan_needed_paise") or facts.get("project_cost_paise") or limit
    principal = min(int(requested), limit)
    frequency = offer["repayment_frequency"]
    count, period = instalments_for(offer["default_tenure_months"], frequency)
    instalment = emi_paise(principal, offer["rate_bps"], count, frequency)
    monthly_instalment = instalment / max(period, 1)
    income = facts.get("annual_family_income_paise")
    emi_ratio = monthly_instalment / (income / 12) if income else BASELINE["emi_to_income"]
    partners = nearby["partners"] if nearby else None
    # Bank-led MUDRA loans behave differently from corporation schemes of the same loan type.
    prior_key = "mudra" if str(result.get("apex_corp", "")).upper().startswith("MUDRA") else result["loan_type"]
    prior = _schema()["hist_sanction_prior_by_loan_type"].get(prior_key, 0.5)
    row = FeatureRow(
        loan_fit=round(requested / limit, 4),
        emi_to_income=round(emi_ratio, 4),
        interest_advantage_pp=(REFERENCE_RATE_BPS - offer["rate_bps"]) / 100,
        doc_readiness=doc_readiness(result["documents_required"], uploaded),
        partners_25km=float(min(len(partners), 10)) if partners is not None else BASELINE["partners_25km"],
        partner_health=max((p["health_score"] for p in partners), default=0) / 100 if partners else
        (0.0 if partners is not None else BASELINE["partner_health"]),
        hist_sanction_rate=float(prior),
        processing_days=float(offer["processing_days"]),
    )
    context = {"emi_pct": round(emi_ratio * 100), "rate": offer["rate_bps"] / 100, "partners": len(partners) if partners is not None else None,
               "days": offer["processing_days"], "assumed_location": partners is None}
    return row, context


REASON_KEY = {"loan_fit": "ranking.reason.loan_fit", "emi_to_income": "ranking.reason.emi_to_income",
              "interest_advantage_pp": "ranking.reason.interest", "doc_readiness": "ranking.reason.doc_readiness",
              "partners_25km": "ranking.reason.partners", "partner_health": "ranking.reason.partner_health",
              "hist_sanction_rate": "ranking.reason.sanction_rate", "processing_days": "ranking.reason.processing_days"}


# A reason is shown only when its sentence is literally true for this option. SHAP values are
# relative, so an option can gain from "instalment" while its instalment is still heavy.
TRUE_WHEN = {
    "loan_fit": lambda f: f["loan_fit"] <= 1.0,
    "emi_to_income": lambda f: f["emi_to_income"] <= 0.4,
    "interest_advantage_pp": lambda f: f["interest_advantage_pp"] >= 2.0,
    "doc_readiness": lambda f: f["doc_readiness"] >= 0.75,
    "partners_25km": lambda f: f["partners_25km"] >= 1,
    "partner_health": lambda f: f["partner_health"] >= 0.6,
    "hist_sanction_rate": lambda f: f["hist_sanction_rate"] >= 0.5,
    "processing_days": lambda f: f["processing_days"] <= 30,
}


def _reasons(contributions: dict[str, float], context: dict[str, Any], features: dict[str, float]) -> list[dict[str, Any]]:
    params = {"emi_to_income": {"pct": context["emi_pct"]}, "interest_advantage_pp": {"rate": context["rate"]},
              "partners_25km": {"count": context["partners"] or 0}, "processing_days": {"days": context["days"]}}
    positive = sorted(((v, k) for k, v in contributions.items() if v > 0.01), reverse=True)
    out = []
    for value, feature in positive:
        if not TRUE_WHEN[feature](features):
            continue
        if feature in ("partners_25km", "partner_health") and context["assumed_location"]:
            continue  # never claim nearby lenders we did not look up
        out.append({"feature": feature, "key": REASON_KEY[feature], "params": params.get(feature, {}),
                    "weight": round(float(value), 3)})
        if len(out) == 2:
            break
    return out


async def rank(results: list[dict[str, Any]], facts: dict[str, Any], nearby_by_code: dict[str, dict[str, Any] | None],
               uploaded: set[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    """Returns eligible results in ranked order, each with a `rank` block, and the method used."""
    if not results:
        return [], "none"
    rows, contexts = [], []
    for r in results:
        row, ctx = features_for(r, facts, nearby_by_code.get(r["code"]), uploaded)
        rows.append(row.vector())
        contexts.append(ctx)

    async def by_model() -> tuple[list[float], list[dict[str, float]], str]:
        import xgboost as xgb

        booster = _booster()
        names = _schema()["features"]
        dm = xgb.DMatrix(np.asarray(rows, dtype=np.float32), feature_names=names)
        contribs = booster.predict(dm, pred_contribs=True)
        scores = contribs.sum(axis=1)
        # SHAP values are relative to the model's expected score; subtract per-feature mean so
        # the reasons compare this option with the others shown, not with the training average.
        centred = contribs[:, :-1] - contribs[:, :-1].mean(axis=0) if len(rows) > 1 else contribs[:, :-1]
        return [float(s) for s in scores], [dict(zip(names, map(float, c), strict=True)) for c in centred], "model"

    async def by_heuristic() -> tuple[list[float], list[dict[str, float]], str]:
        scored = [heuristic_contributions(row) for row in rows]
        return [s for s, _ in scored], [c for _, c in scored], "heuristic"

    (scores, contributions, method), _ = await guarded("ranking_model", by_model, by_heuristic, timeout_s=2.0, attempts=1)
    ranked = []
    for r, score, contrib, ctx, vector in zip(results, scores, contributions, contexts, rows, strict=True):
        features = dict(zip(FEATURES, vector, strict=True))
        ranked.append({**r, "rank": {"score": round(score, 4), "method": method, "reasons": _reasons(contrib, ctx, features),
                                     "features": {k: round(v, 4) for k, v in features.items()}}})
    ranked.sort(key=lambda r: (-r["rank"]["score"], r["offer"]["rate_bps"], r["code"]))
    for position, r in enumerate(ranked, start=1):
        r["rank"]["position"] = position
    return ranked, method
