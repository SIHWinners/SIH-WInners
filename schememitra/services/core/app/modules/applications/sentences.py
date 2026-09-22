"""Server-side rendering of rule-engine sentences (same typed params the web client formats),
for the PDF loan file, SMS and voice read-back."""

from typing import Any

from app.core.i18n import money, t

FIELD_QUESTION = {
    "annual_family_income_paise": "intake.annual_income", "project_cost_paise": "intake.project_cost",
    "loan_needed_paise": "intake.loan_needed", "social_category": "intake.social_category",
    "disability_pct": "intake.disability_pct", "shg_member": "intake.shg_member",
    "course_admitted": "intake.course_admitted", "state_code": "intake.state", "gender": "intake.gender", "age": "intake.age",
}


def render_value(lang: str, typed: dict[str, Any]) -> str:
    value, kind = typed.get("value"), typed.get("type")
    if kind == "money":
        return money(value) if isinstance(value, int) else "—"
    if kind == "category":
        return t(lang, f"options.social_category.{value}")
    if kind == "categories":
        return ", ".join(t(lang, f"options.social_category.{v}") for v in (value or []))
    if kind == "field":
        return t(lang, FIELD_QUESTION.get(str(value), "common.not_answered"))
    return "—" if value is None else str(value)


def render_sentence(lang: str, ref: dict[str, Any] | None) -> str:
    if not ref:
        return ""
    params = {name: render_value(lang, p) for name, p in (ref.get("params") or {}).items()}
    return t(lang, ref["key"], **params)
