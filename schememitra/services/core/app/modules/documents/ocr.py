"""OCR adapters (ADR-009). RapidOCR runs PP-OCR models on ONNX Runtime; the SANDBOX engine
recognises the seeded demo documents by SHA-256 and reports nothing for anything else, which
routes the citizen to DigiLocker or manual entry exactly as a real low-confidence read would."""

import asyncio
import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from app.config import CORE_DIR, get_settings
from app.core.resilience import guarded
from app.logging import get_logger

log = get_logger("ocr")
DEMO_DOCS_DIR = CORE_DIR / "var" / "demo_docs"


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: tuple[int, int, int, int]


@dataclass
class OcrResult:
    lines: list[OcrLine] = field(default_factory=list)
    engine: str = "sandbox"
    sandbox: bool = True

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def mean_confidence(self) -> float:
        return sum(line.confidence for line in self.lines) / len(self.lines) if self.lines else 0.0


class OcrEngine(Protocol):
    async def read(self, image: bytes, original_sha256: str) -> OcrResult: ...


def load_manifest() -> dict[str, Any]:
    path = DEMO_DOCS_DIR / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class SandboxOcr:
    async def read(self, image: bytes, original_sha256: str) -> OcrResult:
        entry = load_manifest().get(original_sha256)
        if not entry:
            return OcrResult([], "sandbox", True)
        return OcrResult([OcrLine(ln["text"], ln["confidence"], tuple(ln["box"])) for ln in entry["lines"]], "sandbox", True)


@lru_cache
def _rapidocr() -> Any:
    from rapidocr_onnxruntime import RapidOCR  # optional extra: `uv sync --extra ocr`

    return RapidOCR()


def warm_rapidocr() -> None:
    _rapidocr()
    print("RapidOCR models loaded")


class RapidOcrEngine:
    async def read(self, image: bytes, original_sha256: str) -> OcrResult:
        def run() -> OcrResult:
            result, _ = _rapidocr()(image)
            lines = []
            for points, text, score in result or []:
                xs = [int(p[0]) for p in points]
                ys = [int(p[1]) for p in points]
                lines.append(OcrLine(text, float(score), (min(xs), min(ys), max(xs), max(ys))))
            return OcrResult(lines, "rapidocr", False)

        return await asyncio.to_thread(run)


async def read_document(image: bytes, original_sha256: str) -> OcrResult:
    sandbox = SandboxOcr()
    if get_settings().ocr_mode != "rapidocr":
        return await sandbox.read(image, original_sha256)

    async def primary() -> OcrResult:
        return await RapidOcrEngine().read(image, original_sha256)

    async def fallback() -> OcrResult:
        return await sandbox.read(image, original_sha256)

    result, _ = await guarded("ocr", primary, fallback, timeout_s=20, attempts=1)
    return result
