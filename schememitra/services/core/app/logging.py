"""Structured JSON logs with automatic PII scrubbing.

Anything that looks like a phone number, Aadhaar number, email or a known name field is
masked before it reaches a handler, so a careless `log.info(payload)` cannot leak PII."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 12-digit Aadhaar, optionally grouped 4-4-4
    (re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"), "[AADHAAR]"),
    # Indian mobile numbers with optional +91 / 0 prefix
    (re.compile(r"(?<![\dA-Za-z])(?:\+?91[ -]?|0)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
]
_SENSITIVE_KEYS = {
    "full_name", "name", "phone", "dob", "aadhaar", "address", "otp", "password",
    "father_name", "token", "authorization", "access_token", "full_name_enc",
}


def scrub_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in _SENSITIVE_KEYS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub_text(record.getMessage()),
        }
        extra = getattr(record, "ctx", None)
        if extra:
            payload["ctx"] = scrub(extra)
        if record.exc_info:
            payload["exc"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    # Windows consoles default to cp1252, which cannot print Indic scripts.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("uvicorn.access", "httpx", "aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
