"""Condition kinds used in scheme YAML. A kind is a readable shorthand ("income_max with
param income_limit_paise") that compiles to explicit JSON-Logic plus sentence metadata.
The compiled logic is what gets stored, shown in the admin trace and shipped offline, so
nothing about eligibility is hidden inside Python code."""

from collections.abc import Callable
from typing import Any

from app.modules.eligibility.engine import Condition

Compiler = Callable[[dict[str, Any]], Condition]


def _max_money(field: str, param_default: str, pass_key: str, fail_key: str, change_key: str) -> Compiler:
    def compile_(spec: dict[str, Any]) -> Condition:
        param = spec.get("param", param_default)
        return Condition(
            id=spec["id"], kind=spec["kind"],
            logic={"<=": [{"var": field}, {"param": param}]},
            fields=[field], pass_key=pass_key, fail_key=fail_key,
            sentence={"value": {"var": field, "type": "money"}, "limit": {"param": param, "type": "money"}},
            change_key=change_key, change={"limit": {"param": param, "type": "money"}},
        )

    return compile_


def _category_in(spec: dict[str, Any]) -> Condition:
    param = spec.get("param", "categories")
    return Condition(
        id=spec["id"], kind="category_in",
        logic={"in": [{"var": "social_category"}, {"param": param}]},
        fields=["social_category"], pass_key="rules.c.category_in", fail_key="rules.c.category_not_in",
        sentence={"value": {"var": "social_category", "type": "category"}, "allowed": {"param": param, "type": "categories"}},
    )


def _age_between(spec: dict[str, Any]) -> Condition:
    return Condition(
        id=spec["id"], kind="age_between",
        logic={"<=": [{"param": "min_age"}, {"var": "age"}, {"param": "max_age"}]},
        fields=["age"], pass_key="rules.c.age_within", fail_key="rules.c.age_outside",
        sentence={"value": {"var": "age", "type": "number"}, "min": {"param": "min_age", "type": "number"},
                  "max": {"param": "max_age", "type": "number"}},
        change_key="rules.change.age_between",
        change={"min": {"param": "min_age", "type": "number"}, "max": {"param": "max_age", "type": "number"}},
    )


def _disability_min(spec: dict[str, Any]) -> Condition:
    return Condition(
        id=spec["id"], kind="disability_min",
        logic={">=": [{"var": "disability_pct"}, {"param": "min_disability_pct"}]},
        fields=["disability_pct"], pass_key="rules.c.disability_ok", fail_key="rules.c.disability_missing",
        sentence={"value": {"var": "disability_pct", "type": "number"}, "min": {"param": "min_disability_pct", "type": "number"}},
    )


def _flag(field: str, expected: Any, pass_key: str, fail_key: str, change_key: str | None, kind: str) -> Compiler:
    def compile_(spec: dict[str, Any]) -> Condition:
        return Condition(
            id=spec["id"], kind=kind, logic={"==": [{"var": field}, expected]}, fields=[field],
            pass_key=pass_key, fail_key=fail_key, change_key=change_key,
        )

    return compile_


def _state_in(spec: dict[str, Any]) -> Condition:
    return Condition(
        id=spec["id"], kind="state_in", logic={"in": [{"var": "state_code"}, {"param": "states"}]},
        fields=["state_code"], pass_key="rules.c.state_ok", fail_key="rules.c.state_fail",
    )


def _custom(spec: dict[str, Any]) -> Condition:
    return Condition(
        id=spec["id"], kind="custom", logic=spec["logic"], fields=spec.get("fields", []),
        pass_key=spec["pass_key"], fail_key=spec["fail_key"], sentence=spec.get("sentence", {}),
        change_key=spec.get("change_key"), change=spec.get("change", {}),
    )


KINDS: dict[str, Compiler] = {
    "income_max": _max_money("annual_family_income_paise", "income_limit_paise", "rules.c.income_within",
                             "rules.c.income_exceeds", "rules.change.income_below"),
    "project_cost_max": _max_money("project_cost_paise", "max_project_cost_paise", "rules.c.project_within",
                                   "rules.c.project_exceeds", "rules.change.project_below"),
    "loan_max": _max_money("loan_needed_paise", "max_loan_paise", "rules.c.loan_within",
                           "rules.c.loan_exceeds", "rules.change.loan_below"),
    "category_in": _category_in,
    "age_between": _age_between,
    "disability_min": _disability_min,
    "women_only": _flag("gender", "female", "rules.c.women_only_ok", "rules.c.women_only_fail", None, "women_only"),
    "shg_member": _flag("shg_member", True, "rules.c.shg_ok", "rules.c.shg_fail", "rules.change.join_shg", "shg_member"),
    "course_admitted": _flag("course_admitted", True, "rules.c.course_ok", "rules.c.course_fail",
                             "rules.change.get_admission", "course_admitted"),
    "state_in": _state_in,
    "custom": _custom,
}


def compile_condition(spec: dict[str, Any]) -> Condition:
    kind = spec["kind"]
    if kind not in KINDS:
        raise ValueError(f"unknown condition kind {kind!r}")
    return KINDS[kind](spec)
