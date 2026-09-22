"""Server-side messages for SMS, voice prompts and the PDF, read from the same catalogues the
web and mobile apps use (packages/i18n), so a string is translated exactly once."""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT

LOCALES = ("en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _i18n_dir() -> Path:
    return Path(os.environ.get("I18N_DIR") or REPO_ROOT / "packages" / "i18n")


@lru_cache
def catalogue(locale: str) -> dict[str, Any]:
    path = _i18n_dir() / "locales" / f"{locale if locale in LOCALES else 'en'}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def glossary() -> dict[str, Any]:
    return json.loads((_i18n_dir() / "glossary.json").read_text(encoding="utf-8"))


def _lookup(messages: dict[str, Any], key: str) -> str | None:
    node: Any = messages
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def t(locale: str, key: str, **params: Any) -> str:
    """Translate with English fallback; unknown placeholders are left visible rather than dropped."""
    text = _lookup(catalogue(locale), key) or _lookup(catalogue("en"), key) or key
    return _PLACEHOLDER.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), text)


def group_indian(rupees: int) -> str:
    digits = str(abs(rupees))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        digits = f"{head},{tail}"
    return ("-" if rupees < 0 else "") + digits


def money(paise: int, show_paise: bool = False) -> str:
    whole, frac = divmod(abs(paise), 100)
    sign = "-" if paise < 0 else ""
    base = f"{sign}₹{group_indian(whole)}"
    return f"{base}.{frac:02d}" if (show_paise or frac) else base


def money_words(locale: str, paise: int) -> str:
    """"1 lakh 25 thousand rupees" with unit words in the user's language (ADR-013)."""
    rupees = abs(paise) // 100
    if rupees == 0:
        return f"0 {t(locale, 'common.rupees')}"
    parts = []
    for size, key in ((10_000_000, "crore"), (100_000, "lakh"), (1_000, "thousand"), (100, "hundred")):
        n, rupees = divmod(rupees, size)
        if n:
            parts.append(f"{n} {t(locale, f'common.{key}')}")
    if rupees:
        parts.append(str(rupees))
    return f"{' '.join(parts)} {t(locale, 'common.rupees')}"
