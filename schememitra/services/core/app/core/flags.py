"""Runtime flags editable from the admin console: adapter modes, chaos toggles and
tunables. Persisted in `feature_flags` and mirrored in memory for hot paths.

Keys:  mode.<setting_name>   e.g. mode.llm_mode = "ollama"
       chaos.<dependency>    e.g. chaos.bhashini_asr = true
       param.<setting_name>  e.g. param.readiness_threshold = 70"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.resilience import set_chaos
from app.db.base import utcnow
from app.db.models import FeatureFlag
from app.db.session import get_sessionmaker
from app.logging import get_logger

log = get_logger("flags")

MUTABLE_MODES = {"bhashini_mode", "digilocker_mode", "sms_mode", "llm_mode", "ocr_mode", "llm_model"}
MUTABLE_PARAMS = {"readiness_threshold", "partner_recovery_floor", "k_anonymity_min", "demo_mode"}
CHAOS_TARGETS = {"bhashini_asr", "bhashini_nmt", "bhashini_tts", "llm", "ocr", "ranking_model", "sms",
                 "map_tiles", "internet", "digilocker"}


def _apply(key: str, value: Any) -> None:
    kind, _, name = key.partition(".")
    settings = get_settings()
    if kind == "chaos" and name in CHAOS_TARGETS:
        set_chaos(name, bool(value))
    elif (kind == "mode" and name in MUTABLE_MODES) or (kind == "param" and name in MUTABLE_PARAMS):
        setattr(settings, name, value)
    else:
        raise ValueError(f"unknown flag {key}")


async def load_flags() -> None:
    try:
        async with get_sessionmaker()() as session:
            rows = (await session.execute(select(FeatureFlag))).scalars().all()
    except Exception:  # noqa: BLE001 - table may not exist before first migration
        log.warning("feature_flags table not ready; using env defaults")
        return
    for row in rows:
        try:
            _apply(row.key, row.value.get("v"))
        except ValueError:
            log.warning("ignoring unknown flag %s", row.key)


async def set_flag(session: AsyncSession, key: str, value: Any, actor: str) -> None:
    _apply(key, value)
    row = await session.get(FeatureFlag, key)
    if row is None:
        session.add(FeatureFlag(key=key, value={"v": value}, updated_by=actor))
    else:
        row.value = {"v": value}
        row.updated_by = actor
        row.updated_at = utcnow()


def current_flags() -> dict[str, Any]:
    from app.core.resilience import registry

    s = get_settings()
    out: dict[str, Any] = {f"mode.{m}": getattr(s, m) for m in sorted(MUTABLE_MODES)}
    out.update({f"param.{p}": getattr(s, p) for p in sorted(MUTABLE_PARAMS)})
    out.update({f"chaos.{c}": c in registry.chaos for c in sorted(CHAOS_TARGETS)})
    return out
