import json
import random
from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.finance.calc import (
    LoanInput,
    affordability,
    build_schedule,
    capitalised_balance,
    emi_paise,
    funding_split,
    round_half_even,
)

getcontext().prec = 60
GOLDEN = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures" / "finance-golden.json"


def decimal_emi(principal: int, rate_bps: int, n: int) -> int:
    """Independent Decimal implementation of the textbook formula, for cross-checking."""
    p = Decimal(principal)
    if rate_bps == 0:
        return int((p / n).quantize(Decimal(1), ROUND_HALF_EVEN))
    r = Decimal(rate_bps) / Decimal(120000)
    f = (1 + r) ** n
    return int((p * r * f / (f - 1)).quantize(Decimal(1), ROUND_HALF_EVEN))


def test_round_half_even() -> None:
    assert round_half_even(5, 2) == 2
    assert round_half_even(7, 2) == 4
    assert round_half_even(-7, 2) == -4
    assert round_half_even(10, 3) == 3
    with pytest.raises(ValueError):
        round_half_even(1, 0)


def test_known_emi_one_lakh_12_percent_12_months() -> None:
    # ₹1,00,000 at 12% for 12 months: textbook EMI ₹8,884.88
    assert emi_paise(100_000_00, 1200, 12) == 888_488


@given(st.integers(100_00, 50_00_000_00), st.integers(0, 2000), st.integers(1, 120))
def test_emi_matches_decimal_formula(principal: int, rate: int, n: int) -> None:
    assert emi_paise(principal, rate, n) == decimal_emi(principal, rate, n)


@given(
    st.integers(10_000_00, 25_00_000_00),
    st.integers(0, 1500),
    st.integers(1, 120),
    st.sampled_from([0, 3, 6, 9, 12]),
    st.sampled_from(["interest_capitalised", "interest_paid_monthly", "interest_waived"]),
    st.sampled_from(["monthly", "quarterly"]),
)
def test_schedule_invariants(principal: int, rate: int, tenure: int, mora: int, treatment: str, freq: str) -> None:
    s = build_schedule(LoanInput(principal, rate, tenure, mora, treatment, freq))  # type: ignore[arg-type]
    repayments = [r for r in s.rows if r.kind == "repayment"]
    assert repayments[-1].closing_paise == 0
    assert sum(r.principal_paise for r in repayments) == s.principal_after_moratorium_paise
    assert s.total_payable_paise == sum(r.payment_paise for r in s.rows)
    assert all(r.payment_paise >= 0 and r.interest_paise >= 0 for r in s.rows)
    if treatment == "interest_capitalised":
        assert s.principal_after_moratorium_paise == capitalised_balance(principal, rate, mora)
        assert s.moratorium_interest_paise == s.principal_after_moratorium_paise - principal
    else:
        assert s.principal_after_moratorium_paise == principal
    if treatment == "interest_waived":
        assert s.moratorium_interest_paise == 0
    # only the last instalment may differ from the EMI (rounding absorption)
    assert all(r.payment_paise == s.instalment_paise for r in repayments[:-1])
    assert abs(repayments[-1].payment_paise - s.instalment_paise) <= s.instalments


def test_savitaben_micro_credit_example() -> None:
    s = build_schedule(LoanInput(60_000_00, 650, 36, 3, "interest_capitalised"))
    assert s.principal_after_moratorium_paise == capitalised_balance(60_000_00, 650, 3)
    assert 60_900_00 < s.principal_after_moratorium_paise < 61_000_00
    assert len(s.rows) == 39


def test_zero_rate_and_subsidy() -> None:
    s = build_schedule(LoanInput(12_000_00, 0, 12, subsidy_paise=2_000_00))
    assert s.principal_paise == 10_000_00 and s.total_interest_paise == 0
    assert s.instalment_paise == round_half_even(10_000_00, 12)


@pytest.mark.parametrize("bad", [
    LoanInput(0, 100, 12), LoanInput(100, -1, 12), LoanInput(100, 100, 0),
    LoanInput(100, 100, 12, moratorium_months=61), LoanInput(100, 100, 12, subsidy_paise=100),
])
def test_invalid_inputs(bad: LoanInput) -> None:
    with pytest.raises(ValueError):
        build_schedule(bad)


def test_funding_split_absorbs_rounding() -> None:
    split = funding_split(4_50_000_01, 9000, 500, 500)
    assert split.apex_paise + split.partner_paise + split.beneficiary_paise == 4_50_000_01
    with pytest.raises(ValueError):
        funding_split(100, 9000, 500, 400)


def test_affordability_suggestions() -> None:
    loan = LoanInput(4_00_000_00, 800, 24, 6)
    s = build_schedule(loan)
    result = affordability(loan, s, monthly_income_paise=20_000_00, max_ratio_bps=4000, max_tenure_months=84)
    assert not result.affordable
    assert result.suggest_tenure_months is not None and result.suggest_tenure_emi_paise <= 8_000_00
    assert result.suggest_principal_paise is not None and result.suggest_principal_paise % 100_000 == 0
    assert result.suggest_principal_emi_paise <= 8_000_00
    too_poor = affordability(loan, s, monthly_income_paise=5_000_00, max_ratio_bps=4000, max_tenure_months=84)
    assert too_poor.suggest_tenure_months is None and too_poor.suggest_principal_paise is not None
    fine = affordability(loan, s, monthly_income_paise=1_00_000_00)
    assert fine.affordable and fine.suggest_tenure_months is None


async def test_emi_api(client) -> None:  # type: ignore[no-untyped-def]
    body = {"principal_paise": 6_000_000, "rate_bps": 650, "tenure_months": 36, "moratorium_months": 3,
            "project_cost_paise": 6_000_000, "split": {"apex_bps": 9000, "partner_bps": 1000, "beneficiary_bps": 0},
            "monthly_income_paise": 1_000_000}
    res = (await client.post("/v1/finance/emi", json=body)).json()
    assert res["split_breakdown"]["apex_paise"] == 5_400_000
    assert len(res["schedule"]) == 39 and res["affordability"]["affordable"] is True
    bad = await client.post("/v1/finance/emi", json={**body, "split": {"apex_bps": 1, "partner_bps": 1, "beneficiary_bps": 1}})
    assert bad.status_code == 422
    cmp = (await client.post("/v1/finance/compare", json={"options": [body, {**body, "tenure_months": 48}]})).json()
    assert cmp["options"][1]["emi_paise"] < cmp["options"][0]["emi_paise"]
    assert cmp["options"][0]["schedule"] == []


def test_write_golden_cases() -> None:
    """Generates the 1,000-case fixture the TypeScript twin must reproduce exactly."""
    rng = random.Random(20260916)
    cases = []
    for _ in range(1000):
        loan = LoanInput(
            principal_paise=rng.randrange(5_000_00, 50_00_000_00),
            rate_bps=rng.choice([0, rng.randrange(400, 1501, 25)]),
            tenure_months=rng.randrange(3, 121),
            moratorium_months=rng.choice([0, 3, 6, 9, 12]),
            treatment=rng.choice(["interest_capitalised", "interest_paid_monthly", "interest_waived"]),
            frequency=rng.choice(["monthly", "monthly", "quarterly"]),
            subsidy_paise=rng.choice([0, 0, 0, 1_000_00]),
        )
        s = build_schedule(loan)
        cases.append({
            "input": loan.__dict__,
            "expect": {"emi": s.instalment_paise, "after_moratorium": s.principal_after_moratorium_paise,
                       "total_interest": s.total_interest_paise, "total_payable": s.total_payable_paise,
                       "rows": len(s.rows), "last_payment": s.rows[-1].payment_paise},
        })
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"_note": "generated by services/core/tests/test_finance.py", "cases": cases}, indent=0)
    if not GOLDEN.exists() or GOLDEN.read_text(encoding="utf-8") != text:
        GOLDEN.write_text(text, encoding="utf-8")
    assert len(cases) == 1000
