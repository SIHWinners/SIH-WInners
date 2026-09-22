"""Health, readiness and adapter status. The status payload drives the SANDBOX badges in
the admin console and the fallback matrix (spec §13)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.jobs import get_queue
from app.core.resilience import registry
from app.db.session import get_session
from app.errors import not_found

router = APIRouter(tags=["system"])


class AdapterStatus(BaseModel):
    name: str
    mode: str
    sandbox: bool
    breaker: str
    chaos: bool
    last_path: str | None
    fallback: str


class SystemStatus(BaseModel):
    env: str
    demo_mode: bool
    database: str
    cache: str
    queue: str
    storage: str
    adapters: list[AdapterStatus]


FALLBACKS: dict[str, str] = {
    "bhashini_asr": "faster-whisper local → typed input",
    "bhashini_nmt": "IndicTrans2 local → glossary templates",
    "bhashini_tts": "pre-generated clips → device TTS",
    "llm": "rule-based slot filling with form UI",
    "ocr": "DigiLocker pull → manual entry beside image",
    "ranking_model": "weighted heuristic scorer",
    "sms": "push notification + in-app timeline",
    "map_tiles": "list view with distances",
    "internet": "offline drafts + offline rules/EMI → SMS submit",
    "digilocker": "camera upload + manual verification at partner",
}


def ranking_mode() -> str:
    from app.modules.ranking.service import model_loaded

    return "xgboost" if model_loaded() else "heuristic"


def adapter_modes() -> dict[str, tuple[str, bool]]:
    s = get_settings()
    return {
        "bhashini_asr": (s.bhashini_mode, s.bhashini_mode != "real"),
        "bhashini_nmt": (s.bhashini_mode, s.bhashini_mode != "real"),
        "bhashini_tts": (s.bhashini_mode, s.bhashini_mode != "real"),
        "llm": (f"{s.llm_mode}:{s.llm_model}" if s.llm_mode != "off" else "off", s.llm_mode == "off"),
        "ocr": (s.ocr_mode, s.ocr_mode == "sandbox"),
        "ranking_model": (ranking_mode(), False),
        "sms": (s.sms_mode, s.sms_mode == "console"),
        "map_tiles": ("osm", False),
        "internet": ("online", False),
        "digilocker": (s.digilocker_mode, s.digilocker_mode != "real"),
    }


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, Any]:
    await session.execute(text("select 1"))
    return {"status": "ready"}


@router.get("/v1/system/status", response_model=SystemStatus)
async def system_status() -> SystemStatus:
    s = get_settings()
    adapters = []
    for name, (mode, sandbox) in adapter_modes().items():
        b = registry.breaker(name)
        adapters.append(AdapterStatus(
            name=name, mode=mode, sandbox=sandbox, breaker=b.state, chaos=name in registry.chaos,
            last_path=registry.last_path.get(name), fallback=FALLBACKS[name],
        ))
    return SystemStatus(
        env=s.env, demo_mode=s.demo_mode,
        database="sqlite (local profile)" if s.is_sqlite else "postgresql+postgis",
        cache="redis" if s.redis_url else "memory",
        queue=type(get_queue()).__name__,
        storage=f"{s.storage_mode} (AES-256-GCM)",
        adapters=adapters,
    )


@router.get("/v1/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    state = await get_queue().get(job_id)
    if state is None:
        raise not_found("job")
    return {"id": state.id, "status": state.status, "result": state.result, "error": state.error}
