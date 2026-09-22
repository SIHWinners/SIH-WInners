from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.i18n import LOCALES


class SessionIn(BaseModel):
    lang: str = Field(default="en", max_length=8, description=f"one of {', '.join(LOCALES)}")


class SlotOut(BaseModel):
    value: Any
    confidence: float
    method: str
    display: str


class ClarifyOut(BaseModel):
    slot: str
    value: Any
    display: str


class DistrictHQ(BaseModel):
    """District headquarters, used as the search centre for nearby lenders (same as the typed form)."""

    lat: float
    lng: float
    pincode: str


class VoiceTurnOut(BaseModel):
    session_id: str
    lang: str
    state: Literal["intake", "clarify", "confirm", "done"]
    turn: int
    max_turns: int
    transcript: str | None = None
    transcript_engine: Literal["bhashini", "whisper", "sandbox", "typed"] | None = None
    sandbox: bool = False
    reply_text: str
    reply_audio_url: str | None = None
    tts: Literal["clip", "bhashini", "device"] = "device"
    slots: dict[str, SlotOut]
    asked: list[str]
    changed: list[str] = []
    clarify: ClarifyOut | None = None
    handoff: Literal["rules", "form"] | None = None
    district_hq: DistrictHQ | None = None
    filled: int
    total: int
    elapsed_ms: int
    processing_ms: int
    demo_utterances: list[str] = []
    asr_available: bool = True


class ReadbackIn(BaseModel):
    application_id: str


class ReadbackOut(BaseModel):
    text: str
    audio_url: str | None = None
    tts: Literal["clip", "bhashini", "device"] = "device"
    demo_reply: str | None = None


class ReadbackReplyOut(BaseModel):
    intent: Literal["confirm", "correct", "unclear"]
    field: str | None = None
    transcript: str
    transcript_engine: Literal["bhashini", "whisper", "sandbox", "typed"]
    sandbox: bool = False
    reply_text: str
    evidence: dict[str, Any] = {}
