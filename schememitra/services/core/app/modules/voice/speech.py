"""ASR / translation / TTS adapters with the §13 fallback chain, each behind `guarded()`
(timeout, retry, circuit breaker, admin chaos toggle).

  ASR   Bhashini (real, or SANDBOX scripted transcript) → faster-whisper local → typed input
  NMT   Bhashini → glossary templates (replies are pre-localised, so nothing visible changes)
  TTS   cached clip (pre-generated for static prompts) → Bhashini → device voice

Audio is processed in memory and discarded after transcription; it is never stored."""

import asyncio
import hashlib
import importlib.util
import re
from dataclasses import dataclass
from functools import cache
from typing import Any

from app.config import get_settings
from app.core.i18n import glossary
from app.core.resilience import guarded, registry
from app.core.storage import get_storage
from app.logging import get_logger
from app.modules.voice import bhashini
from app.modules.voice.demo import scripted

log = get_logger("voice")
AUDIO_TYPES = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/mp4": "mp4",
               "audio/mpeg": "mp3", "audio/aac": "aac"}
MAX_AUDIO_BYTES = 2_000_000  # a 15 s chunk is ~25 KB as Opus, ~480 KB as 16 kHz WAV
WHISPER_LANGS = {"en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "ml", "pa", "as"}


class AsrUnavailable(RuntimeError):
    """No speech engine could produce a transcript; the UI switches to typing."""


@dataclass
class Transcript:
    text: str
    engine: str  # bhashini | whisper | sandbox
    sandbox: bool


# --- ASR ------------------------------------------------------------------------------------

def whisper_available() -> bool:
    return get_settings().asr_fallback == "whisper" and importlib.util.find_spec("faster_whisper") is not None


@cache
def _whisper_model() -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(get_settings().whisper_model, device="cpu", compute_type="int8")


def warm_whisper() -> None:
    if whisper_available():
        _whisper_model()


def _whisper_transcribe(audio: bytes, lang: str) -> str:
    import io

    segments, _ = _whisper_model().transcribe(io.BytesIO(audio), language=lang if lang in WHISPER_LANGS else None,
                                              vad_filter=True, beam_size=1)
    return " ".join(seg.text.strip() for seg in segments).strip()


async def transcribe(audio: bytes, content_type: str, lang: str, script_index: int) -> Transcript:
    fmt = AUDIO_TYPES.get(content_type.split(";")[0].strip(), "webm")

    async def primary() -> Transcript:
        if bhashini.configured():
            return Transcript(await bhashini.asr(audio, lang, fmt), "bhashini", False)
        line = scripted(lang, script_index)
        if line is None:
            raise AsrUnavailable(f"no SANDBOX script for {lang}")
        return Transcript(line, "sandbox", True)

    async def fallback() -> Transcript:
        if whisper_available() and lang in WHISPER_LANGS:
            text = await asyncio.to_thread(_whisper_transcribe, audio, lang)
            if text:
                return Transcript(text, "whisper", False)
        raise AsrUnavailable("speech recognition unavailable")

    result, _ = await guarded("bhashini_asr", primary, fallback, timeout_s=4.0, attempts=1)
    return result


# --- translation with glossary protection ---------------------------------------------------

_PLACEHOLDER = "⟦G{}⟧"


def protect(text: str, source: str) -> tuple[str, list[str]]:
    """Swap glossary terms for placeholders so machine translation cannot garble them."""
    terms: list[str] = []
    for entry_key, entry in glossary().items():
        if entry_key.startswith("_"):
            continue
        phrase = entry.get(source)
        if phrase and phrase in text:
            text = text.replace(phrase, _PLACEHOLDER.format(len(terms)))
            terms.append(entry_key)
    return text, terms


def restore(text: str, terms: list[str], target: str) -> str:
    for i, entry_key in enumerate(terms):
        entry = glossary()[entry_key]
        text = re.sub(re.escape(_PLACEHOLDER.format(i)), entry.get(target, entry["en"]), text)
    return text


async def translate(text: str, source: str, target: str) -> tuple[str | None, str]:
    """Returns (translation or None, engine). None means: keep working in the source language."""
    if source == target:
        return text, "identity"
    protected, terms = protect(text, source)

    async def primary() -> tuple[str | None, str]:
        if not bhashini.configured():
            raise bhashini.BhashiniNotConfigured("sandbox")
        return restore(await bhashini.translate(protected, source, target), terms, target), "bhashini"

    async def fallback() -> tuple[str | None, str]:
        return None, "glossary"

    if not bhashini.configured():
        registry.last_path["bhashini_nmt"] = "sandbox"
        return await fallback()
    result, _ = await guarded("bhashini_nmt", primary, fallback, timeout_s=4.0, attempts=1)
    return result


# --- TTS ------------------------------------------------------------------------------------

def tts_key(text: str, lang: str) -> str:
    return hashlib.sha256(f"{lang}|female|{text}".encode()).hexdigest()


async def cached_clip(digest: str) -> bytes | None:
    storage = get_storage()
    try:
        if not await storage.exists(f"tts/{digest}.wav"):
            return None
        return await storage.get(f"tts/{digest}.wav")
    except Exception:  # noqa: BLE001 - a broken cache entry is just a miss
        return None


async def speak(text: str, lang: str) -> tuple[str | None, str]:
    """Returns (audio URL or None, mode). mode "device" tells the client to use its own voice."""
    digest = tts_key(text, lang)
    if await cached_clip(digest) is not None:
        return f"/v1/voice/tts/{digest}", "clip"

    async def primary() -> tuple[str | None, str]:
        if not bhashini.configured():
            raise bhashini.BhashiniNotConfigured("sandbox")
        audio = await bhashini.tts(text, lang)
        await get_storage().put(f"tts/{digest}.wav", audio)
        return f"/v1/voice/tts/{digest}", "bhashini"

    async def fallback() -> tuple[str | None, str]:
        return None, "device"

    if not bhashini.configured():
        # SANDBOX: no synthetic voice service; the device voice reads the text (labelled in the UI).
        registry.last_path["bhashini_tts"] = "sandbox"
        return await fallback()
    result, _ = await guarded("bhashini_tts", primary, fallback, timeout_s=4.0, attempts=1)
    return result
