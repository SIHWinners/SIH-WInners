"""Transparent weighted scorer: the §13 fallback when the XGBoost model is unavailable, and a
baseline the model is measured against. Contributions are relative to a typical option so
they read as reasons ("lower instalment than usual") in exactly the way SHAP values do."""

from typing import Any

import numpy as np

from app.modules.ranking.features import FEATURES

# Reference option: what an average eligible scheme looks like.
BASELINE = {"loan_fit": 1.0, "emi_to_income": 0.3, "interest_advantage_pp": 4.0, "doc_readiness": 0.7, "partners_25km": 3.0,
            "partner_health": 0.7, "hist_sanction_rate": 0.5, "processing_days": 35.0}


def _terms(v: dict[str, Any]) -> dict[str, float]:
    return {
        "loan_fit": -2.0 * max(0.0, v["loan_fit"] - 1.0),
        "emi_to_income": -4.0 * max(0.0, v["emi_to_income"] - 0.3) - 0.5 * v["emi_to_income"],
        "interest_advantage_pp": 0.05 * v["interest_advantage_pp"],
        "doc_readiness": 1.5 * v["doc_readiness"],
        "partners_25km": 0.1 * min(v["partners_25km"], 5.0),
        "partner_health": 1.2 * v["partner_health"],
        "hist_sanction_rate": 1.5 * v["hist_sanction_rate"],
        "processing_days": -0.01 * v["processing_days"],
    }


_BASE_TERMS = _terms(BASELINE)


def heuristic_contributions(row: list[float]) -> tuple[float, dict[str, float]]:
    values = dict(zip(FEATURES, row, strict=True))
    terms = _terms(values)
    contributions = {k: terms[k] - _BASE_TERMS[k] for k in FEATURES}
    return sum(contributions.values()), contributions


def heuristic_scores(X: np.ndarray) -> np.ndarray:
    return np.asarray([heuristic_contributions([float(x) for x in row])[0] for row in X])
