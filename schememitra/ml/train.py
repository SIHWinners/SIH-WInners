"""Train the scheme ranker: XGBoost LambdaMART (rank:ndcg) on SYNTHETIC data.

    uv run --project services/core python ml/train.py

Reproducible (fixed seeds). Prints NDCG@3 against baselines and a sanction-rate parity
check across gender and category, writes the model, feature schema and metrics next to
the serving code, and regenerates ml/MODEL_CARD.md from the measured numbers."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core"))
sys.path.insert(0, str(Path(__file__).parent))

from synth import FEATURES as SYNTH_FEATURES  # noqa: E402
from synth import SCHEME_TYPES, generate  # noqa: E402

from app.modules.ranking.features import FEATURES  # noqa: E402
from app.modules.ranking.heuristic import heuristic_scores  # noqa: E402

assert FEATURES == SYNTH_FEATURES, "training and serving feature lists differ"
OUT = ROOT / "services" / "core" / "app" / "modules" / "ranking" / "model"
SEED = 2026
PARAMS = {"objective": "rank:ndcg", "eval_metric": "ndcg@3", "eta": 0.08, "max_depth": 4, "min_child_weight": 5,
          "subsample": 0.9, "colsample_bytree": 0.9, "lambdarank_pair_method": "topk", "lambdarank_num_pair_per_sample": 3,
          "seed": SEED, "nthread": 4, "tree_method": "hist",
          # Domain guard rails: a costlier instalment, a longer wait or a bigger over-limit ask can never
          # raise a score; cheaper money, readier papers, more and healthier lenders can never lower it.
          "monotone_constraints": "(-1,-1,1,1,1,1,1,-1)"}
ROUNDS = 250


def groups(qid: np.ndarray) -> list[int]:
    _, counts = np.unique(qid, return_counts=True)
    return counts.tolist()


def ndcg_at(y: np.ndarray, scores: np.ndarray, qid: np.ndarray, k: int = 3) -> float:
    total, n = 0.0, 0
    for q in np.unique(qid):
        idx = np.where(qid == q)[0]
        rel = y[idx]
        order = np.argsort(-scores[idx], kind="stable")[:k]
        ideal = np.sort(rel)[::-1][:k]
        disc = 1 / np.log2(np.arange(2, k + 2))
        dcg = float(((2.0 ** rel[order] - 1) * disc[: len(order)]).sum())
        idcg = float(((2.0 ** ideal - 1) * disc[: len(ideal)]).sum())
        if idcg > 0:
            total += dcg / idcg
            n += 1
    return total / max(n, 1)


def top1_sanction_by_group(scores: np.ndarray, qid: np.ndarray, prob: np.ndarray, attr: list[str]) -> dict[str, float]:
    by: dict[str, list[float]] = {}
    for q in np.unique(qid):
        idx = np.where(qid == q)[0]
        best = idx[int(np.argmax(scores[idx]))]
        by.setdefault(attr[idx[0]], []).append(float(prob[best]))
    return {g: round(float(np.mean(v)), 4) for g, v in sorted(by.items())}


def parity(rates: dict[str, float]) -> float:
    return round(min(rates.values()) / max(rates.values()), 3)


def main() -> None:
    ds = generate(seed=SEED)
    rng = np.random.default_rng(SEED)
    applicants = np.unique(ds.qid)
    test_ids = set(rng.choice(applicants, size=len(applicants) // 5, replace=False).tolist())
    test = np.array([q in test_ids for q in ds.qid])
    train = ~test  # rows stay grouped by applicant: qid is sorted in generation order

    dtrain = xgb.DMatrix(ds.X[train], label=ds.y[train], feature_names=FEATURES)
    dtrain.set_group(groups(ds.qid[train]))
    dtest = xgb.DMatrix(ds.X[test], label=ds.y[test], feature_names=FEATURES)
    dtest.set_group(groups(ds.qid[test]))
    booster = xgb.train(PARAMS, dtrain, num_boost_round=ROUNDS, evals=[(dtest, "test")], verbose_eval=False)

    Xt, yt, qt, pt = ds.X[test], ds.y[test], ds.qid[test], ds.sanctioned[test]
    gender = [g for g, keep in zip(ds.gender, test, strict=True) if keep]
    category = [c for c, keep in zip(ds.category, test, strict=True) if keep]
    model_scores = booster.predict(dtest, output_margin=True)
    heuristic = heuristic_scores(Xt)
    rate_first = Xt[:, FEATURES.index("interest_advantage_pp")]  # today's default order: cheapest money first
    random_scores = np.random.default_rng(SEED).random(len(yt))

    # TreeSHAP sanity: contributions add up to the margin for every row.
    contribs = booster.predict(dtest, pred_contribs=True)
    shap_ok = bool(np.allclose(contribs.sum(axis=1), model_scores, atol=1e-3))

    metrics = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"), "seed": SEED, "rows": int(len(ds.y)),
        "applicants": int(len(applicants)), "test_applicants": len(test_ids), "rounds": ROUNDS, "params": PARAMS,
        "ndcg@3": {"model": round(ndcg_at(yt, model_scores, qt), 4), "heuristic": round(ndcg_at(yt, heuristic, qt), 4),
                   "rate_first": round(ndcg_at(yt, rate_first, qt), 4), "random": round(ndcg_at(yt, random_scores, qt), 4)},
        "top1_latent_sanction": {
            name: {"overall": round(float(np.mean(list(top1_sanction_by_group(s, qt, pt, ["all"] * len(qt)).values()))), 4),
                   "gender": top1_sanction_by_group(s, qt, pt, gender), "category": top1_sanction_by_group(s, qt, pt, category)}
            for name, s in (("model", model_scores), ("heuristic", heuristic), ("rate_first", rate_first))
        },
        "shap_additivity": shap_ok,
        "feature_importance_gain": {k: round(v, 2) for k, v in sorted(booster.get_score(importance_type="gain").items(),
                                                                      key=lambda kv: -kv[1])},
    }
    for name in ("model", "heuristic", "rate_first"):
        block = metrics["top1_latent_sanction"][name]
        block["parity_gender"] = parity(block["gender"])
        block["parity_category"] = parity(block["category"])

    OUT.mkdir(parents=True, exist_ok=True)
    booster.save_model(OUT / "ranker.json")
    priors = {k: round(sum(v["sanction"]) / 2, 3) for k, v in SCHEME_TYPES.items()}
    (OUT / "feature_schema.json").write_text(json.dumps({
        "model": "xgboost rank:ndcg (LambdaMART)", "version": datetime.now(UTC).strftime("%Y%m%d"), "features": FEATURES,
        "hist_sanction_prior_by_loan_type": priors, "synthetic": True,
    }, indent=2) + "\n", encoding="utf-8")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    write_model_card(metrics)
    print(json.dumps({k: metrics[k] for k in ("rows", "ndcg@3", "shap_additivity")}, indent=2))
    for name in ("model", "heuristic", "rate_first"):
        b = metrics["top1_latent_sanction"][name]
        print(f"{name:>10}: top-1 sanction {b['overall']:.3f} · parity gender {b['parity_gender']} · category {b['parity_category']}")


def write_model_card(m: dict) -> None:
    t = m["top1_latent_sanction"]

    def rows(block: str) -> str:
        groups_ = list(t["model"][block])
        head = "| Ranker | " + " | ".join(groups_) + " | parity (min/max) |\n|---|" + "---|" * (len(groups_) + 1) + "\n"
        return head + "\n".join(
            f"| {name} | " + " | ".join(f"{t[name][block][g]:.3f}" for g in groups_) + f" | {t[name]['parity_' + block]} |"
            for name in ("model", "heuristic", "rate_first"))

    ndcg = m["ndcg@3"]
    fair_ok = t["model"]["parity_gender"] >= 0.8 and t["model"]["parity_category"] >= 0.8
    card = f"""# Model card — SchemeMitra scheme ranker

> Generated by `ml/train.py` on {m['trained_at']} (seed {m['seed']}). Numbers below are measured, not typed.

## What it does
Orders the schemes a person is **already eligible for** so the one most likely to reach sanction comes first, and explains
why in plain language (TreeSHAP → sentence templates). It never decides eligibility (that is the published rule set)
and never decides sanction (that is the lender). If the model is unavailable, a transparent weighted heuristic serves
the same list with simpler reasons (spec §13).

## Model
- XGBoost `rank:ndcg` (LambdaMART), {m['rounds']} rounds, depth {m['params']['max_depth']}, eta {m['params']['eta']}.
- Features ({len(FEATURES)}): {', '.join('`' + f + '`' for f in FEATURES)}.
- **Not features:** gender, social category, religion, disability, name, location identifiers.

## Data — SYNTHETIC
{m['rows']:,} applicant–scheme rows for {m['applicants']:,} simulated applicants from `ml/synth.py`. No real applicant data was
used. Outcomes come from a documented latent sanction probability, so the model learns our assumptions about what makes a
file succeed (affordability, papers, lender health and supply, past sanction rates, processing time). Group attributes are
simulated with lower incomes and thinner lender access for some groups so that the fairness check has something to find.
**Before any real use the model must be retrained and re-audited on pilot outcomes** (docs/PILOT_PLAN.md).

## Evaluation (held-out {m['test_applicants']:,} applicants)
| Ranker | NDCG@3 |
|---|---|
| XGBoost model | {ndcg['model']} |
| Weighted heuristic (fallback) | {ndcg['heuristic']} |
| Cheapest rate first (rule default) | {ndcg['rate_first']} |
| Random | {ndcg['random']} |

Mean latent sanction probability of the first-ranked scheme: model {t['model']['overall']}, heuristic
{t['heuristic']['overall']}, cheapest rate first {t['rate_first']['overall']}. The model optimises the graded outcome, where
a sanction within 30 days scores highest, so it sometimes puts a faster scheme above one with a slightly higher sanction
chance. Outcomes are graded so that a sanction with an affordable instalment (≤ 40% of monthly income) counts more than
a stretched one. Monotone constraints keep the model sensible: instalment burden, over-limit asks and processing time can
only lower a score; cheaper money, readier papers and more, healthier nearby lenders can only raise it.

TreeSHAP additivity check (contributions sum to the model margin): **{'pass' if m['shap_additivity'] else 'FAIL'}**.

Feature importance (gain): {', '.join(f'`{k}` {v}' for k, v in m['feature_importance_gain'].items())}.

## Fairness — sanction-rate parity of the top recommendation
Mean latent sanction probability of the scheme ranked first, by group. Parity = lowest group ÷ highest group
(four-fifths rule: ≥ 0.8).

### Gender
{rows('gender')}

### Social category
{rows('category')}

Result: **{'within the 0.8 threshold' if fair_ok else 'BELOW the 0.8 threshold — do not ship without mitigation'}**.
Differences that remain come from the simulated income and lender-access gaps, which no ranking of eligible schemes can
remove; the ranker should not *widen* them relative to the rule default, which the table lets reviewers check.

## Limits and risks
- Trained on synthetic data; real outcomes will differ.
- `hist_sanction_rate` uses a per-loan-type prior until the pilot produces observed rates.
- `doc_readiness` uses planning assumptions about paper availability until uploads replace them.
- Monitoring in production: NDCG@3 on decided applications, parity per district each month, drift of feature distributions.

## Owners
Team brain.exe_crashed (SIH 2026, PS 26092). Reviewed with the apex corporation during the pilot.
"""
    (ROOT / "ml" / "MODEL_CARD.md").write_text(card, encoding="utf-8")


if __name__ == "__main__":
    main()
