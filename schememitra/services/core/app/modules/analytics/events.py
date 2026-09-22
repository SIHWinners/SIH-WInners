"""Anonymised analytics events (spec §8, §9.10). Only buckets and codes — never a name, phone,
exact income, exact age, application id or tracking id — so the policy dashboard cannot be
joined back to a person."""

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent

INCOME_BUCKETS = [(0, "0-1L"), (100_000_00, "1-2L"), (200_000_00, "2-3L"), (300_000_00, "3-5L"), (500_000_01, "5L+")]
AGE_BUCKETS = [(0, "<18"), (18, "18-25"), (26, "26-35"), (36, "36-45"), (46, "46-60"), (61, "60+")]


def bucket(value: int | None, buckets: list[tuple[int, str]]) -> str | None:
    if value is None:
        return None
    label = None
    for lower, name in buckets:
        if value >= lower:
            label = name
    return label


def age_from(dob_iso: str | None, today: date | None = None) -> int | None:
    if not dob_iso:
        return None
    born = date.fromisoformat(dob_iso)
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


async def record(
    session: AsyncSession, event: str, *, step: str | None = None, lang: str | None = None, facts: dict[str, Any] | None = None,
    scheme_code: str | None = None, partner_type: str | None = None, reason_code: str | None = None, value: float | None = None,
) -> None:
    f = facts or {}
    session.add(AnalyticsEvent(
        event=event, step=step, lang=lang, state_code=f.get("state_code"), district_code=f.get("district_code"),
        scheme_code=scheme_code, partner_type=partner_type, social_category=f.get("social_category"),
        gender=f.get("gender"), bucketed_age=bucket(f.get("age"), AGE_BUCKETS),
        bucketed_income=bucket(f.get("annual_family_income_paise"), INCOME_BUCKETS), reason_code=reason_code, value=value,
    ))
