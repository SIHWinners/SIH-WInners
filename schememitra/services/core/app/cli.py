"""Operational commands: `python -m app.cli <command>`."""

import asyncio
import json
import sys
from pathlib import Path


def export_openapi(target: str) -> None:
    from app.main import create_app

    spec = create_app().openapi()
    Path(target).write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI written to {target} ({len(spec['paths'])} paths)")


async def audit_verify() -> int:
    from app.core.audit import verify_chain
    from app.db.session import dispose_engine, get_sessionmaker

    async with get_sessionmaker()() as session:
        report = await verify_chain(session)
    await dispose_engine()
    if report.ok:
        print(f"audit chain OK — {report.checked} entries verified")
        return 0
    print(f"audit chain BROKEN at seq {report.broken_at_seq} after {report.checked} good entries")
    return 1


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    command, *args = sys.argv[1:] or ["help"]
    if command == "export-openapi":
        export_openapi(args[0] if args else "openapi.json")
    elif command == "audit-verify":
        raise SystemExit(asyncio.run(audit_verify()))
    elif command == "warm-ocr":
        from app.modules.documents.ocr import warm_rapidocr

        warm_rapidocr()
    elif command == "warm-asr":
        from app.modules.voice.speech import warm_whisper

        warm_whisper()
    elif command == "warm-tts":
        raise SystemExit(asyncio.run(warm_tts()))
    else:
        print("commands: export-openapi <path> | audit-verify | warm-ocr | warm-asr | warm-tts")


async def warm_tts() -> int:
    """Pre-generate audio clips for every static voice prompt in all 13 languages (needs Bhashini)."""
    from app.core.i18n import LOCALES, catalogue, t
    from app.modules.voice import bhashini, speech

    if not bhashini.configured():
        print("BHASHINI_MODE is not real: skipping clip generation; clients use the device voice (SANDBOX)")
        return 0
    keys = ["voice.greeting", "voice.ack", "voice.not_understood", "voice.confirm_all", "voice.done", "voice.correct_which",
            "voice.finish_on_form", *(f"voice.ask.{k}" for k in catalogue("en")["voice"]["ask"])]
    made = 0
    for lang in LOCALES:
        for key in keys:
            _, mode = await speech.speak(t(lang, key), lang)
            made += mode == "bhashini"
    print(f"generated {made} clips")
    return 0


if __name__ == "__main__":
    main()
