"""Rule engine tests. CI enforces 100% line coverage on app.modules.eligibility.engine."""

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.eligibility.engine import (
    Condition,
    RuleError,
    evaluate_condition,
    evaluate_logic,
    evaluate_scheme,
    validate_logic,
)
from app.modules.eligibility.kinds import compile_condition

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "packages" / "contracts" / "fixtures" / "jsonlogic-cases.json").read_text(
        encoding="utf-8"
    )
)
LAKH = 100_000 * 100  # paise


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: json.dumps(c["logic"])[:60])
def test_shared_fixture(case: dict) -> None:
    assert evaluate_logic(case["logic"], case["data"], case.get("params")) == case["expect"]


@pytest.mark.parametrize("case", FIXTURE["errors"], ids=lambda c: json.dumps(c["logic"])[:40])
def test_shared_fixture_errors(case: dict) -> None:
    with pytest.raises(RuleError):
        evaluate_logic(case["logic"], {}, {})


def test_non_numeric_arithmetic_is_rejected() -> None:
    with pytest.raises(TypeError):
        evaluate_logic({"+": [1, "2"]}, {})
    with pytest.raises(TypeError):
        evaluate_logic({"*": [True, 2]}, {})


def test_validate_logic_dry_run() -> None:
    validate_logic({"<=": [{"var": "x"}, {"param": "p"}]}, {"p": 1})
    with pytest.raises(RuleError):
        validate_logic({"<=": [{"var": "x"}, {"param": "q"}]}, {"p": 1})


INCOME = compile_condition({"id": "income", "kind": "income_max"})
PARAMS = {"income_limit_paise": 5 * LAKH, "categories": ["sc"], "max_loan_paise": 2 * LAKH, "min_age": 18, "max_age": 50}


def test_income_boundary_exact_limit_passes_and_one_rupee_more_fails() -> None:
    at_limit = evaluate_condition(INCOME, {"annual_family_income_paise": 5 * LAKH}, PARAMS)
    over = evaluate_condition(INCOME, {"annual_family_income_paise": 5 * LAKH + 100}, PARAMS)
    zero = evaluate_condition(INCOME, {"annual_family_income_paise": 0}, PARAMS)
    missing = evaluate_condition(INCOME, {}, PARAMS)
    assert at_limit["result"] == "pass" and at_limit["sentence"]["key"] == "rules.c.income_within"
    assert over["result"] == "fail" and over["sentence"]["key"] == "rules.c.income_exceeds"
    assert over["change"] == {"key": "rules.change.income_below",
                              "params": {"limit": {"type": "money", "value": 5 * LAKH}}}
    assert zero["result"] == "pass"
    assert missing["result"] == "unknown" and missing["sentence"]["key"] == "rules.c.missing_value"
    assert at_limit["sentence"]["params"]["value"] == {"type": "money", "value": 5 * LAKH}


@given(st.integers(min_value=0, max_value=10**12))
def test_income_rule_matches_arithmetic(income: int) -> None:
    row = evaluate_condition(INCOME, {"annual_family_income_paise": income}, PARAMS)
    assert row["result"] == ("pass" if income <= 5 * LAKH else "fail")


@given(st.integers(min_value=0, max_value=120))
def test_age_between_is_inclusive(age: int) -> None:
    cond = compile_condition({"id": "age", "kind": "age_between"})
    row = evaluate_condition(cond, {"age": age}, PARAMS)
    assert row["result"] == ("pass" if 18 <= age <= 50 else "fail")


def test_scheme_statuses_and_near_miss() -> None:
    conditions = [compile_condition({"id": "category", "kind": "category_in"}), INCOME,
                  compile_condition({"id": "loan", "kind": "loan_max"})]
    good = {"social_category": "sc", "annual_family_income_paise": 180_000_00, "loan_needed_paise": LAKH}
    assert evaluate_scheme(conditions, good, PARAMS)["status"] == "eligible"

    edge = {**good, "annual_family_income_paise": 5 * LAKH + 100}
    out = evaluate_scheme(conditions, edge, PARAMS)
    assert out["status"] == "ineligible" and out["failed"] == ["income"]
    assert out["near_miss"]["id"] == "income"

    two_fails = {**edge, "loan_needed_paise": 3 * LAKH}
    assert evaluate_scheme(conditions, two_fails, PARAMS)["near_miss"] is None

    wrong_group = {**good, "social_category": "obc"}
    wrong = evaluate_scheme(conditions, wrong_group, PARAMS)
    assert wrong["failed"] == ["category"] and wrong["near_miss"] is None  # category cannot "change"

    partial = {"social_category": "sc"}
    info = evaluate_scheme(conditions, partial, PARAMS)
    assert info["status"] == "needs_info"
    assert info["missing"] == ["annual_family_income_paise", "loan_needed_paise"]


def test_flag_kinds_and_custom() -> None:
    women = compile_condition({"id": "w", "kind": "women_only"})
    assert evaluate_condition(women, {"gender": "female"}, {})["result"] == "pass"
    assert evaluate_condition(women, {"gender": "male"}, {})["sentence"]["key"] == "rules.c.women_only_fail"
    shg = compile_condition({"id": "s", "kind": "shg_member"})
    assert evaluate_condition(shg, {"shg_member": False}, {})["change"]["key"] == "rules.change.join_shg"
    disability = compile_condition({"id": "d", "kind": "disability_min"})
    assert evaluate_condition(disability, {"disability_pct": 40}, {"min_disability_pct": 40})["result"] == "pass"
    state = compile_condition({"id": "st", "kind": "state_in"})
    assert evaluate_condition(state, {"state_code": "GJ"}, {"states": ["GJ", "RJ"]})["result"] == "pass"
    custom = compile_condition({"id": "c", "kind": "custom", "logic": {">": [{"var": "age"}, 20]}, "fields": ["age"],
                                "pass_key": "k.ok", "fail_key": "k.no"})
    assert evaluate_condition(custom, {"age": 21}, {})["sentence"]["key"] == "k.ok"
    with pytest.raises(ValueError):
        compile_condition({"id": "x", "kind": "astrology"})


def test_condition_without_fields_always_evaluates() -> None:
    cond = Condition(id="always", kind="custom", logic={"==": [1, 1]}, fields=[], pass_key="a", fail_key="b")
    assert evaluate_condition(cond, {}, {})["result"] == "pass"
