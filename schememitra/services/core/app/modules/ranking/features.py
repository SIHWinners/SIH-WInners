"""Ranking features (spec §9.4). Shared by training (ml/train.py) and serving so the two
can never drift. Every feature describes how well a scheme *fits* the applicant; none of
them is gender, caste, religion or disability status (those only decide eligibility,
through the published rules). Fairness is then measured, not assumed (ml/MODEL_CARD.md)."""

from dataclasses import astuple, dataclass, fields
from typing import Any

FEATURES = ["loan_fit", "emi_to_income", "interest_advantage_pp", "doc_readiness", "partners_25km", "partner_health",
            "hist_sanction_rate", "processing_days"]

# How often each paper is already at hand for applicants in the target group (planning
# assumptions for the pilot, replaced by observed upload rates once live).
DOC_AVAILABILITY = {"aadhaar": 0.97, "bank_passbook": 0.9, "income_certificate": 0.75, "caste_certificate": 0.7,
                    "project_quotation": 0.65, "shg_certificate": 0.6, "disability_certificate": 0.55,
                    "admission_letter": 0.6, "marksheet": 0.8}
REFERENCE_RATE_BPS = 1200  # typical informal-to-MFI benchmark the concessional rate is compared with


@dataclass
class FeatureRow:
    loan_fit: float  # requested / scheme limit (≤1 fits; >1 means the limit caps the loan)
    emi_to_income: float  # instalment as a share of monthly family income
    interest_advantage_pp: float  # percentage points below the 12% reference
    doc_readiness: float  # 0..1, papers likely at hand (or actually uploaded)
    partners_25km: float  # healthy lenders for this scheme within 25 km (capped at 10)
    partner_health: float  # best nearby lender's health score 0..1
    hist_sanction_rate: float  # past sanction rate for this scheme (synthetic prior until live data)
    processing_days: float

    def vector(self) -> list[float]:
        return [float(v) for v in astuple(self)]


assert [f.name for f in fields(FeatureRow)] == FEATURES


def doc_readiness(documents_required: list[dict[str, Any]], uploaded: set[str] | None = None) -> float:
    required = [d["type"] for d in documents_required if d.get("required", True)]
    if not required:
        return 1.0
    score = sum(1.0 if uploaded and t in uploaded else DOC_AVAILABILITY.get(t, 0.6) for t in required)
    return round(score / len(required), 3)
