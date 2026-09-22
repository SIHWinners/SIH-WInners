"""Voice sessions: persistence, the ASR → slots → reply → TTS turn, and the read-back.

Turn text and slots are stored encrypted (they contain the person's name); audio is never
stored. Anonymous sessions that never became an application are deleted after 24 hours."""

import json
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_str, encrypt_str
from app.core.i18n import LOCALES, money_words, t
from app.core.security import Principal
from app.db.base import utcnow
from app.db.models import Applicant, Application, Conversation, Partner
from app.errors import ProblemError, not_found
from app.modules.eligibility.loader import get_ruleset
from app.modules.routing.districts import BY_CODE
from app.modules.voice import llm, speech
from app.modules.voice.conversation import MAX_TURNS, ConversationState, display_value, greeting, required_slots, step
from app.modules.voice.demo import READBACK_CONFIRM, SCRIPTS
from app.modules.voice.slots import field_mentioned, yes_no

RETENTION = timedelta(hours=24)


def _load(conv: Conversation) -> tuple[ConversationState, list[dict[str, Any]]]:
    blob = conv.extracted_slots.get("enc")
    state = ConversationState.from_json(json.loads(decrypt_str(blob) or "{}")) if blob else ConversationState(conv.lang)
    turns = [{**turn, "text": decrypt_str(turn["text"])} for turn in conv.turns or []]
    return state, turns


def _save(conv: Conversation, state: ConversationState, turns: list[dict[str, Any]]) -> None:
    conv.extracted_slots = {"enc": encrypt_str(json.dumps(state.to_json(), ensure_ascii=False))}
    conv.turns = [{**turn, "text": encrypt_str(turn["text"])} for turn in turns]
    conv.state = state.state
    conv.pending_slot = state.asked[0] if state.asked else None


def _assert_owner(conv: Conversation, principal: Principal | None) -> None:
    if conv.user_id and (principal is None or (principal.user_id != conv.user_id and principal.role != "admin")):
        raise not_found("voice session")


def _district_hq(code: str | None) -> dict[str, Any] | None:
    district = BY_CODE.get(code or "")
    return {"lat": district.lat, "lng": district.lng, "pincode": district.pincode} if district else None


async def _out(conv: Conversation, state: ConversationState, reply: str, *, transcript: str | None = None,
               engine: str | None = None, sandbox: bool = False, changed: list[str] | None = None,
               started: float | None = None) -> dict[str, Any]:
    audio_url, tts_mode = await speech.speak(reply, state.lang)
    values = state.values
    required = required_slots(values)
    clarify = None
    if state.clarify:
        clarify = {"slot": state.clarify["slot"], "value": state.clarify["value"],
                   "display": display_value(state.lang, state.clarify["slot"], state.clarify["value"])}
    return {
        "session_id": str(conv.id), "lang": state.lang, "state": state.state, "turn": state.user_turns, "max_turns": MAX_TURNS,
        "transcript": transcript, "transcript_engine": engine, "sandbox": sandbox, "reply_text": reply,
        "reply_audio_url": audio_url, "tts": tts_mode,
        "slots": {k: {**v, "display": display_value(state.lang, k, v["value"])} for k, v in state.slots.items()}, "asked": state.asked, "changed": changed or [],
        "clarify": clarify, "handoff": state.handoff, "district_hq": _district_hq(values.get("district_code")), "filled": sum(1 for s in required if s in values), "total": len(required),
        "elapsed_ms": int((utcnow() - conv.started_at).total_seconds() * 1000),
        "processing_ms": int((time.perf_counter() - started) * 1000) if started else 0,
        "demo_utterances": SCRIPTS.get(state.lang, []),
        "asr_available": speech.bhashini.configured() or state.lang in SCRIPTS or speech.whisper_available(),
    }


async def create_session(session: AsyncSession, lang: str, principal: Principal | None) -> dict[str, Any]:
    await session.execute(delete(Conversation).where(Conversation.application_id.is_(None),
                                                      Conversation.started_at < utcnow() - RETENTION))
    lang = lang if lang in LOCALES else "en"
    conv = Conversation(lang=lang, user_id=principal.user_id if principal else None, turns=[], extracted_slots={})
    state = ConversationState(lang)
    reply = greeting(state)
    turns = [{"role": "assistant", "text": reply, "at": utcnow().isoformat(timespec="seconds")}]
    _save(conv, state, turns)
    session.add(conv)
    await session.flush()
    return await _out(conv, state, reply)


async def get_conversation(session: AsyncSession, session_id: UUID, principal: Principal | None) -> Conversation:
    conv = await session.get(Conversation, session_id)
    if conv is None:
        raise not_found("voice session")
    _assert_owner(conv, principal)
    return conv


async def current(session: AsyncSession, conv: Conversation) -> dict[str, Any]:
    state, turns = _load(conv)
    last = next((turn["text"] for turn in reversed(turns) if turn["role"] == "assistant"), "")
    return await _out(conv, state, last)


async def _transcribe(audio: bytes | None, content_type: str | None, text: str | None, lang: str, index: int) -> tuple[str, str, bool]:
    if text is not None and text.strip():
        return text.strip()[:500], "typed", False
    if not audio:
        raise ProblemError(422, "Say something or type an answer", "voice.not_understood")
    if len(audio) > speech.MAX_AUDIO_BYTES:
        raise ProblemError(413, "Audio chunk too large", "errors.upload_too_large")
    if (content_type or "").split(";")[0].strip() not in speech.AUDIO_TYPES:
        raise ProblemError(415, "Unsupported audio format", "errors.unsupported_file")
    try:
        result = await speech.transcribe(audio, content_type or "audio/webm", lang, index)
    except speech.AsrUnavailable as err:
        raise ProblemError(503, "Speech recognition unavailable", "voice.asr_unavailable") from err
    finally:
        del audio  # never persisted
    return result.text, result.engine, result.sandbox


async def utterance(session: AsyncSession, conv: Conversation, *, text: str | None, audio: bytes | None,
                    content_type: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    state, turns = _load(conv)
    if state.state == "done":
        return await _out(conv, state, t(state.lang, "voice.done"), started=started)
    script_index = len(SCRIPTS.get(state.lang, [])) - 1 if state.state == "confirm" else state.user_turns
    transcript, engine, sandbox = await _transcribe(audio, content_type, text, state.lang, script_index)

    llm_slots = {}
    if state.state == "intake":
        llm_slots = await llm.extract(transcript, state.lang, state.values.get("full_name"), state.missing())
    reply = step(state, transcript, llm_slots)
    now = utcnow().isoformat(timespec="seconds")
    turns += [{"role": "user", "text": transcript, "engine": engine, "at": now},
              {"role": "assistant", "text": reply.text, "at": now}]
    _save(conv, state, turns)
    await session.flush()
    return await _out(conv, state, reply.text, transcript=transcript, engine=engine, sandbox=sandbox,
                      changed=reply.changed, started=started)


# --- read-back (C6) -------------------------------------------------------------------------

async def readback_text(session: AsyncSession, app: Application, applicant: Applicant) -> str:
    lang = app.lang
    finance = app.finance_summary or {}
    plan = finance.get("plan", {})
    scheme_code = (app.eligibility_trace or {}).get("scheme_code")
    ruleset = await get_ruleset(session)
    doc = ruleset.schemes[scheme_code].doc if scheme_code in ruleset.schemes else {"name": {"en": scheme_code or "—"}}
    partner = await session.get(Partner, app.partner_id) if app.partner_id else None
    return t(lang, "send.readback_summary",
             name=applicant.full_name_enc or "—", scheme=doc["name"].get(lang, doc["name"]["en"]),
             amount=money_words(lang, int(plan.get("principal_paise", 0))),
             emi=money_words(lang, int(finance.get("emi_paise", 0))),
             tenure=plan.get("tenure_months", 0), moratorium=plan.get("moratorium_months", 0),
             partner=(partner.name if partner else "—").replace(" (demo)", ""))


async def readback(session: AsyncSession, app: Application, applicant: Applicant) -> dict[str, Any]:
    text = await readback_text(session, app, applicant)
    audio_url, mode = await speech.speak(text, app.lang)
    return {"text": text, "audio_url": audio_url, "tts": mode, "demo_reply": READBACK_CONFIRM.get(app.lang)}


async def readback_reply(session: AsyncSession, app: Application, applicant: Applicant, *, text: str | None,
                         audio: bytes | None, content_type: str | None) -> dict[str, Any]:
    lang = app.lang
    lines = SCRIPTS.get(lang, [])
    transcript, engine, sandbox = await _transcribe(audio, content_type, text, lang, max(len(lines) - 1, 0))
    field = field_mentioned(transcript)
    answer = yes_no(transcript)
    if answer is True and field is None:
        summary = await readback_text(session, app, applicant)
        evidence = {"readback_text": summary, "voice_confirmation": transcript, "transcript_engine": engine,
                    "confirmed_at": utcnow().isoformat(timespec="seconds"), "language": lang}
        return {"intent": "confirm", "field": None, "transcript": transcript, "transcript_engine": engine, "sandbox": sandbox,
                "reply_text": t(lang, "voice.readback_confirmed", text=transcript), "evidence": evidence}
    if field or answer is False:
        return {"intent": "correct", "field": field, "transcript": transcript, "transcript_engine": engine,
                "sandbox": sandbox, "reply_text": t(lang, "voice.correct_which")}
    return {"intent": "unclear", "field": None, "transcript": transcript, "transcript_engine": engine, "sandbox": sandbox,
            "reply_text": t(lang, "voice.not_understood")}
