"""SYNTHETIC training data for the scheme ranker (spec §9.4). No real applicant data exists
for this problem yet, so we simulate applicant–scheme–outcome rows from documented
assumptions. The model therefore learns *our assumptions*, and the model card says so.

Each applicant gets 4–6 eligible scheme options. The outcome for an option is drawn from a
latent sanction probability that rises with affordability, paper readiness, lender health,
historical sanction rate and nearby lender supply, and falls when the loan exceeds the
scheme limit, no lender is within reach, or processing is slow. Relevance label: 3 sanctioned
with an instalment the household can carry (≤ 40% of monthly income), 2 sanctioned but
stretched (a default risk, so worth less), 1 documents requested, 0 rejected.

Group attributes (gender, category) are generated for the fairness audit only; they are
never model features. Income and lender access vary by group the way they do in the field,
which is exactly what the parity check has to catch."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FEATURES = ["loan_fit", "emi_to_income", "interest_advantage_pp", "doc_readiness", "partners_25km", "partner_health",
            "hist_sanction_rate", "processing_days"]
# Loan types and their typical parameters (mirrors the seeded rule set in services/core/rules).
SCHEME_TYPES = {
    "micro_finance": {"rate_bps": (400, 600), "limit": 125_000, "days": (15, 35), "sanction": (0.55, 0.75), "docs": 0.8},
    "term_loan": {"rate_bps": (600, 900), "limit": 1_500_000, "days": (30, 75), "sanction": (0.35, 0.6), "docs": 0.65},
    "women_scheme": {"rate_bps": (400, 500), "limit": 150_000, "days": (15, 40), "sanction": (0.5, 0.75), "docs": 0.75},
    "group_loan": {"rate_bps": (400, 600), "limit": 1_000_000, "days": (25, 60), "sanction": (0.45, 0.7), "docs": 0.6},
    "education_loan": {"rate_bps": (300, 600), "limit": 1_500_000, "days": (20, 50), "sanction": (0.5, 0.7), "docs": 0.7},
    "mudra": {"rate_bps": (900, 1200), "limit": 500_000, "days": (20, 60), "sanction": (0.3, 0.5), "docs": 0.7},
}
GROUPS = {"gender": ["female", "male"], "category": ["sc", "st", "obc", "safai_karamchari", "minority"]}


@dataclass
class Dataset:
    X: np.ndarray
    y: np.ndarray
    qid: np.ndarray
    gender: list[str]
    category: list[str]
    sanctioned: np.ndarray
    scheme_type: list[str]


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 1200
    return principal / months if r == 0 else principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def latent_probability(f: dict[str, float]) -> float:
    z = (-1.6
         - 7.0 * max(0.0, f["emi_to_income"] - 0.3)
         - 3.0 * max(0.0, f["loan_fit"] - 1.0)
         + 2.2 * f["doc_readiness"]
         + 1.8 * f["partner_health"]
         + 2.4 * f["hist_sanction_rate"]
         + 0.18 * min(f["partners_25km"], 5.0)
         + 0.06 * f["interest_advantage_pp"]
         - 0.012 * f["processing_days"]
         - (2.5 if f["partners_25km"] == 0 else 0.0))  # nobody nearby to take the file
    return 1 / (1 + math.exp(-z))


def generate(n_applicants: int = 10_000, seed: int = 2026) -> Dataset:
    rng = np.random.default_rng(seed)
    rows, labels, qids, genders, categories, sanctioned, types = [], [], [], [], [], [], []
    for applicant in range(n_applicants):
        gender = rng.choice(GROUPS["gender"], p=[0.52, 0.48])
        category = rng.choice(GROUPS["category"], p=[0.3, 0.2, 0.35, 0.05, 0.1])
        # Field reality the parity check must notice: lower incomes and thinner lender access
        # for ST and Safai Karamchari households, slightly lower incomes for women.
        income_shift = {"st": -0.18, "safai_karamchari": -0.22}.get(category, 0.0) - (0.06 if gender == "female" else 0.0)
        access_shift = {"st": -1.2, "safai_karamchari": -0.6}.get(category, 0.0)
        annual_income = float(np.clip(rng.lognormal(math.log(150_000) + income_shift, 0.45), 30_000, 500_000))
        requested = float(np.clip(rng.lognormal(math.log(200_000), 0.9), 15_000, 2_500_000))
        n_options = int(rng.integers(4, 7))  # 4–6 options, ~50k rows for 10k applicants
        options = rng.choice(list(SCHEME_TYPES), size=n_options, replace=True)
        for kind in options:
            p = SCHEME_TYPES[kind]
            rate_bps = float(rng.uniform(*p["rate_bps"]))
            months = int(rng.choice([24, 36, 48, 60, 84]))
            principal = min(requested, p["limit"])
            f = {
                "loan_fit": requested / p["limit"],
                "emi_to_income": emi(principal, rate_bps / 100, months) / (annual_income / 12),
                "interest_advantage_pp": (1200 - rate_bps) / 100,
                "doc_readiness": float(np.clip(rng.normal(p["docs"], 0.12), 0.2, 1.0)),
                "partners_25km": float(np.clip(rng.poisson(max(0.3, 4 + access_shift)), 0, 10)),
                "partner_health": float(np.clip(rng.beta(6, 2.5) - (0.05 if access_shift < -1 else 0), 0.2, 1.0)),
                "hist_sanction_rate": float(rng.uniform(*p["sanction"])),
                "processing_days": float(rng.uniform(*p["days"])),
            }
            prob = latent_probability(f)
            draw = rng.random()
            if draw < prob:
                label = 3 if f["emi_to_income"] <= 0.4 else 2
            elif draw < prob + (1 - prob) * 0.35:
                label = 1
            else:
                label = 0
            rows.append([f[k] for k in FEATURES])
            labels.append(label)
            qids.append(applicant)
            genders.append(str(gender))
            categories.append(str(category))
            sanctioned.append(prob)
            types.append(str(kind))
    return Dataset(np.asarray(rows, dtype=np.float32), np.asarray(labels), np.asarray(qids), genders, categories,
                   np.asarray(sanctioned), types)


def write_csv(ds: Dataset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["qid", *FEATURES, "label", "gender", "category", "scheme_type", "latent_sanction_prob"])
        for i in range(len(ds.y)):
            w.writerow([ds.qid[i], *[round(float(v), 4) for v in ds.X[i]], ds.y[i], ds.gender[i], ds.category[i],
                        ds.scheme_type[i], round(float(ds.sanctioned[i]), 4)])


if __name__ == "__main__":
    data = generate()
    out = Path(__file__).parent / "data" / "synthetic_rankings.csv"
    write_csv(data, out)
    print(f"wrote {len(data.y)} SYNTHETIC rows for {len(set(data.qid.tolist()))} applicants → {out}")
