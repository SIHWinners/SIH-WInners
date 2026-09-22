"""~150 fictional channel partners (3 per district HQ across 5 states) with six months of
metrics. Names end in "(demo)" and use invented bank names so nothing can be mistaken for a
real branch. Deterministic (seeded RNG), so demos and tests see the same partners."""

import math
import random
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Partner, PartnerMetric
from app.modules.eligibility.loader import load_rule_files
from app.modules.routing.districts import DISTRICTS, District

RRB_NAMES = {"GJ": "Narmada Kisan Gramin Bank", "RJ": "Thar Gramin Bank", "UP": "Gomti Gramin Bank",
             "MH": "Sahyadri Gramin Bank", "TN": "Vaigai Gramin Bank"}
PSB_NAME = "Janseva National Bank"
MFI_NAME = "Sakhi Udyam Microfinance"
PERIODS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
RADIUS = {"SCA": 60, "PSB": 25, "RRB": 40, "NBFC_MFI": 30}
DOCS = {
    "SCA": ["aadhaar", "caste_certificate", "income_certificate", "bank_passbook", "project_quotation"],
    "PSB": ["aadhaar", "bank_passbook", "income_certificate", "project_quotation"],
    "RRB": ["aadhaar", "bank_passbook", "caste_certificate", "project_quotation"],
    "NBFC_MFI": ["aadhaar", "bank_passbook", "shg_certificate"],
}
HOURS = {"SCA": "Mon–Fri 10:00–17:00", "PSB": "Mon–Sat 10:00–16:00", "RRB": "Mon–Sat 10:00–15:30",
         "NBFC_MFI": "Mon–Sat 09:30–17:30"}


@dataclass(frozen=True)
class Profile:
    """Shape of a partner's metrics; overrides pin down demo-critical partners."""
    recovery: tuple[float, float] = (0.78, 0.96)
    npa: tuple[float, float] = (1.5, 9.0)
    days: tuple[float, float] = (12, 45)
    used: tuple[float, float] = (0.35, 0.85)
    pending: tuple[int, int] = (5, 90)


# (district, type) → (offset km north, offset km east, profile)
OVERRIDES: dict[tuple[str, str], tuple[float, float, Profile]] = {
    # Ramesh (C4): the nearest bank has a weak repayment record this quarter and is skipped.
    ("RJ-BAR", "PSB"): (0.4, 0.5, Profile(recovery=(0.60, 0.63), npa=(14, 16), used=(0.5, 0.6))),
    ("RJ-BAR", "SCA"): (2.1, -1.6, Profile(recovery=(0.93, 0.96), npa=(1.5, 2.5), days=(14, 18), used=(0.4, 0.5))),
    ("RJ-BAR", "RRB"): (-3.8, 2.9, Profile(recovery=(0.84, 0.88), days=(25, 30))),
    # Savitaben: strong SCA in Dahod; the micro-lender has used up this quarter's funds.
    ("GJ-DAH", "SCA"): (1.2, 0.8, Profile(recovery=(0.94, 0.97), npa=(1.0, 2.0), days=(10, 14), used=(0.3, 0.4))),
    ("GJ-DAH", "NBFC_MFI"): (0.6, -0.9, Profile(recovery=(0.88, 0.9), used=(1.0, 1.0))),
    ("TN-MDU", "SCA"): (1.5, 1.0, Profile(recovery=(0.92, 0.95), days=(12, 16), used=(0.3, 0.45))),
    ("UP-LKO", "SCA"): (2.0, -1.2, Profile(recovery=(0.9, 0.94), days=(15, 20), used=(0.35, 0.5))),
}


def _types_for(index: int) -> list[str]:
    return ["SCA", "PSB", "RRB" if index % 2 == 0 else "NBFC_MFI"]


def _name(d: District, kind: str) -> str:
    if kind == "SCA":
        return f"{d.name} District SCA Branch (demo)"
    if kind == "PSB":
        return f"{PSB_NAME} — {d.name} (demo)"
    if kind == "RRB":
        return f"{RRB_NAMES[d.state_code]} — {d.name} (demo)"
    return f"{MFI_NAME} — {d.name} (demo)"


async def seed_partners(session: AsyncSession) -> str:
    rules = load_rule_files()
    schemes_by_type = {t: sorted(r["scheme_code"] for r in rules if t in r["channel_partner_types"])
                       for t in ("SCA", "PSB", "RRB", "NBFC_MFI")}
    all_categories = ["sc", "st", "obc", "safai_karamchari", "minority", "general"]
    categories = {"SCA": all_categories, "PSB": all_categories, "RRB": all_categories,
                  "NBFC_MFI": ["sc", "obc", "safai_karamchari", "general"]}

    rng = random.Random(51)  # team id — any fixed seed works
    existing = {p.name: p for p in (await session.execute(select(Partner))).scalars()}
    count = 0
    for i, district in enumerate(DISTRICTS):
        for kind in _types_for(i):
            north, east, profile = OVERRIDES.get(
                (district.code, kind), (rng.uniform(-6, 6), rng.uniform(-6, 6), Profile())
            )
            name = _name(district, kind)
            partner = existing.get(name) or Partner(name=name)
            partner.type = kind
            partner.state_code = district.state_code
            partner.district_code = district.code
            partner.district_name = district.name
            partner.address = f"Main Road, {district.name}, {district.pincode} (fictional demo address)"
            partner.lat = round(district.lat + north / 111.0, 6)
            partner.lng = round(district.lng + east / (111.0 * math.cos(math.radians(district.lat))), 6)
            partner.service_radius_km = RADIUS[kind]
            partner.schemes_supported = schemes_by_type[kind]
            partner.categories_supported = categories[kind]
            partner.languages = list(district.languages)
            partner.documents_needed = DOCS[kind]
            partner.open_hours = HOURS[kind]
            partner.contact = {"phone": f"1800-000-{1000 + count:04d}", "note": "demo number"}
            partner.is_demo = True
            if partner.id is None:
                session.add(partner)
            await session.flush()

            await session.execute(delete(PartnerMetric).where(PartnerMetric.partner_id == partner.id))
            allocated = rng.choice([50, 75, 100, 150, 250, 400]) * 100_000_00  # ₹ lakh → paise
            recovery = rng.uniform(*profile.recovery)
            # About one in twelve ordinary partners slips below the recovery floor, so C4 shows up
            # in more places than the scripted demo partner.
            if (district.code, kind) not in OVERRIDES and rng.random() < 0.08:
                recovery = rng.uniform(0.55, 0.69)
            for m, period in enumerate(PERIODS):
                drift = (m - len(PERIODS) + 1) * 0.005
                used_ratio = min(1.0, rng.uniform(*profile.used) * (0.7 + 0.05 * m))
                if profile.used[0] >= 1.0:
                    used_ratio = 1.0
                session.add(PartnerMetric(
                    partner_id=partner.id, period=period,
                    recovery_rate=round(max(0.0, min(1.0, recovery + drift)), 3),
                    npa_pct=round(rng.uniform(*profile.npa), 2),
                    avg_sanction_days=round(rng.uniform(*profile.days), 1),
                    funds_allocated_paise=allocated,
                    funds_disbursed_paise=int(allocated * used_ratio),
                    pending_applications=rng.randint(*profile.pending),
                ))
            count += 1
    return f"{count} partners, {count * len(PERIODS)} monthly metric rows"
