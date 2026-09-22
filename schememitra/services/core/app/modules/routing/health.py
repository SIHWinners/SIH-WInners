"""Partner Health Score and smart fund routing (spec §9.6, claim C4).

score = 100 × (0.35·recovery + 0.20·(1 − npa_norm) + 0.20·capacity_left + 0.15·speed + 0.10·(1 − backlog_norm))

Hard exclusions come before scoring and are always shown to the citizen with the reason,
so "skip lenders with weak repayment records" is visible, not silent."""

import math
from dataclasses import dataclass

WEIGHTS = {"recovery": 0.35, "npa": 0.20, "capacity": 0.20, "speed": 0.15, "backlog": 0.10}
NPA_CEILING_PCT = 20.0  # NPA at or above this counts as the worst case
FASTEST_DAYS, SLOWEST_DAYS = 7.0, 90.0
BACKLOG_CEILING = 150
DISTANCE_DECAY_KM = 15.0


@dataclass(frozen=True)
class Metrics:
    recovery_rate: float
    npa_pct: float
    avg_sanction_days: float
    funds_allocated_paise: int
    funds_disbursed_paise: int
    pending_applications: int


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def components(m: Metrics) -> dict[str, float]:
    capacity_left = 0.0 if m.funds_allocated_paise <= 0 else 1 - m.funds_disbursed_paise / m.funds_allocated_paise
    return {
        "recovery": _clamp(m.recovery_rate),
        "npa": 1 - _clamp(m.npa_pct / NPA_CEILING_PCT),
        "capacity": _clamp(capacity_left),
        "speed": 1 - _clamp((m.avg_sanction_days - FASTEST_DAYS) / (SLOWEST_DAYS - FASTEST_DAYS)),
        "backlog": 1 - _clamp(m.pending_applications / BACKLOG_CEILING),
    }


def health_score(m: Metrics) -> tuple[int, dict[str, float]]:
    parts = components(m)
    score = 100 * sum(WEIGHTS[k] * v for k, v in parts.items())
    return round(score), {k: round(v, 3) for k, v in parts.items()}


def exclusion_reason(m: Metrics, recovery_floor: float, requested_paise: int | None) -> str | None:
    if m.recovery_rate < recovery_floor:
        return "low_recovery"
    remaining = m.funds_allocated_paise - m.funds_disbursed_paise
    if remaining <= 0 or (requested_paise is not None and remaining < requested_paise):
        return "capacity_exhausted"
    return None


def rank_score(health: int, distance_km: float) -> float:
    return round(health / 100 * math.exp(-distance_km / DISTANCE_DECAY_KM), 4)
