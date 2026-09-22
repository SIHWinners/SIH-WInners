"""Nearby partner search: spatial candidates → hard exclusions → health score → distance decay."""

import time
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.cache import get_cache
from app.db.models import Partner, PartnerMetric
from app.modules.routing.geo import bounding_box, geohash, haversine_km
from app.modules.routing.health import Metrics, exclusion_reason, health_score, rank_score

CANDIDATE_LIMIT = 50

KNN_SQL = text("""
    SELECT p.id, ST_Distance(p.geom::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) / 1000.0 AS km
    FROM partners p
    WHERE p.deleted_at IS NULL
      AND ST_DWithin(p.geom::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius_m)
    ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
    LIMIT :limit
""")


async def _candidates(session: AsyncSession, lat: float, lng: float, radius_km: float) -> list[tuple[Partner, float]]:
    if get_settings().is_sqlite:
        s, n, w, e = bounding_box(lat, lng, radius_km)
        rows = (
            await session.execute(
                select(Partner).where(Partner.deleted_at.is_(None), Partner.lat.between(s, n), Partner.lng.between(w, e))
            )
        ).scalars().all()
        scored = [(p, haversine_km(lat, lng, p.lat, p.lng)) for p in rows]
        scored = [(p, d) for p, d in scored if d <= radius_km]
        scored.sort(key=lambda pd: pd[1])
        return scored[:CANDIDATE_LIMIT]
    # PostGIS: GiST-backed KNN ordering (spec §9.6).
    hits = (await session.execute(KNN_SQL, {"lat": lat, "lng": lng, "radius_m": radius_km * 1000,
                                            "limit": CANDIDATE_LIMIT})).all()
    if not hits:
        return []
    by_id = {p.id: p for p in (await session.execute(select(Partner).where(Partner.id.in_([h.id for h in hits])))).scalars()}
    return [(by_id[h.id], float(h.km)) for h in hits if h.id in by_id]


async def latest_metrics(session: AsyncSession, partner_ids: list[UUID]) -> dict[UUID, PartnerMetric]:
    if not partner_ids:
        return {}
    latest = (
        select(PartnerMetric.partner_id, func.max(PartnerMetric.period).label("period"))
        .where(PartnerMetric.partner_id.in_(partner_ids))
        .group_by(PartnerMetric.partner_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(PartnerMetric).join(
                latest, (PartnerMetric.partner_id == latest.c.partner_id) & (PartnerMetric.period == latest.c.period)
            )
        )
    ).scalars().all()
    return {m.partner_id: m for m in rows}


def _as_metrics(m: PartnerMetric | None) -> Metrics:
    if m is None:  # a partner with no reported metrics is treated as unproven, not healthy
        return Metrics(0.0, 20.0, 90.0, 0, 0, 150)
    return Metrics(m.recovery_rate, m.npa_pct, m.avg_sanction_days, m.funds_allocated_paise,
                   m.funds_disbursed_paise, m.pending_applications)


def partner_card(p: Partner, distance_km: float, metrics: PartnerMetric | None) -> dict[str, Any]:
    score, parts = health_score(_as_metrics(metrics))
    return {
        "id": str(p.id), "name": p.name, "type": p.type, "state_code": p.state_code, "district_code": p.district_code,
        "district_name": p.district_name, "address": p.address, "lat": p.lat, "lng": p.lng,
        "distance_km": round(distance_km, 1), "languages": p.languages, "documents_needed": p.documents_needed,
        "open_hours": p.open_hours, "contact": p.contact, "schemes_supported": p.schemes_supported,
        "categories_supported": p.categories_supported, "is_demo": p.is_demo,
        "health_score": score, "health_components": parts,
        "avg_sanction_days": round(metrics.avg_sanction_days) if metrics else None,
        "rank_score": rank_score(score, distance_km),
    }


async def nearby(
    session: AsyncSession, *, lat: float, lng: float, scheme: str | None, category: str | None, radius_km: float,
    loan_paise: int | None, limit: int = 10,
) -> dict[str, Any]:
    started = time.perf_counter()
    settings = get_settings()
    key = f"partners:{geohash(lat, lng)}:{scheme}:{category}:{int(radius_km)}:{loan_paise or 0}:{settings.partner_recovery_floor}"
    cache = get_cache()
    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cache": "hit", "took_ms": round((time.perf_counter() - started) * 1000, 1)}

    candidates = await _candidates(session, lat, lng, radius_km)
    metrics = await latest_metrics(session, [p.id for p, _ in candidates])
    ranked, excluded = [], []
    for partner, km in candidates:
        m = metrics.get(partner.id)
        card = partner_card(partner, km, m)
        reason: str | None = None
        if scheme and scheme not in partner.schemes_supported:
            reason = "scheme_unsupported"
        elif category and category not in partner.categories_supported:
            reason = "category_unsupported"
        elif km > partner.service_radius_km:
            reason = "out_of_radius"
        else:
            reason = exclusion_reason(_as_metrics(m), settings.partner_recovery_floor, loan_paise)
        if reason:
            # Only health-based skips and near-by mismatches are shown, nearest first.
            excluded.append({**card, "reason": reason})
        else:
            ranked.append(card)
    ranked.sort(key=lambda c: (-c["rank_score"], c["distance_km"]))
    result = {
        "engine": "haversine" if settings.is_sqlite else "postgis",
        "center": {"lat": lat, "lng": lng}, "radius_km": radius_km,
        "partners": ranked[:limit],
        "excluded": [e for e in excluded if e["reason"] in ("low_recovery", "capacity_exhausted")][:limit]
        + [e for e in excluded if e["reason"] not in ("low_recovery", "capacity_exhausted")][:3],
    }
    await cache.set(key, result, settings.partner_cache_ttl_s)
    return {**result, "cache": "miss", "took_ms": round((time.perf_counter() - started) * 1000, 1)}


async def invalidate_partner_cache() -> None:
    await get_cache().delete_prefix("partners:")
