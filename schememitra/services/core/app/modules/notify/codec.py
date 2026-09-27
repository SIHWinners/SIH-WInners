"""SMS codec — Python twin of packages/contracts/src/sms-codec.ts (claim C13).

Wire format: ``SM1*<ref><part><total>*<payload>*<crc>`` — every character, separators included,
is in the GSM-7 basic alphabet so one application costs exactly one SMS segment. Both implementations are tested
against the same fixture (packages/contracts/fixtures/sms-cases.json) so a message written
by the phone always decodes the same way on the server."""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

VERSION = "SM1"
MAX_PARTS = 3
PART_CHARS = 160
PART_RE = re.compile(r"^SM1\*([0-9A-Z]{2})([1-3])([1-3])\*(.*)\*([0-9A-Z]{4})$")
STATUS_RE = re.compile(r"^\s*status\s+([A-Za-z0-9-]+)\s*$", re.IGNORECASE)
HELP_RE = re.compile(r"^\s*help\b", re.IGNORECASE)

FIELDS: dict[str, str] = {
    "n": "full_name", "a": "age", "g": "gender", "c": "social_category", "s": "state_code", "d": "district_code",
    "p": "pincode", "i": "annual_family_income_rupees", "e": "education_level", "w": "business_type",
    "k": "project_cost_rupees", "l": "loan_needed_rupees", "sh": "shg_member", "x": "existing_loans",
    "dis": "has_disability", "ph": "phone", "lg": "lang",
}
GENDER = {"f": "female", "m": "male", "o": "other"}
CATEGORY = {"sc": "sc", "st": "st", "ob": "obc", "sk": "safai_karamchari", "mi": "minority", "ge": "general"}
INTS = {"age", "annual_family_income_rupees", "project_cost_rupees", "loan_needed_rupees"}
BOOLS = {"shg_member", "existing_loans", "has_disability"}
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def crc16(text: str) -> int:
    crc = 0xFFFF
    for char in text:
        crc ^= ord(char) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def base36(value: int, width: int = 4) -> str:
    out = ""
    while value:
        value, rem = divmod(value, 36)
        out = _B36[rem] + out
    return (out or "0").rjust(width, "0")


def checksum(payload: str) -> str:
    return base36(crc16(payload))


@dataclass
class Part:
    ref: str
    part: int
    total: int
    body: str
    crc: str


@dataclass
class Decoded:
    kind: Literal["apply", "status", "help", "partial", "unknown"]
    facts: dict[str, Any] = field(default_factory=dict)
    tracking_id: str | None = None
    ref: str | None = None
    parts: int = 0
    received: list[int] = field(default_factory=list)
    reason: str | None = None


def parse_part(text: str) -> Part | None:
    m = PART_RE.match(text.strip())
    if not m:
        return None
    return Part(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5))


def decode_facts(payload: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for pair in payload.split(";"):
        key, sep, raw = pair.partition("=")
        field_name = FIELDS.get(key.strip())
        raw = raw.strip()
        if not sep or not field_name or raw == "":
            continue
        if field_name == "gender":
            if raw in GENDER:
                facts["gender"] = GENDER[raw]
        elif field_name == "social_category":
            if raw in CATEGORY:
                facts["social_category"] = CATEGORY[raw]
        elif field_name in BOOLS:
            facts[field_name] = raw == "1"
        elif field_name in INTS:
            try:
                facts[field_name] = int(float(raw))
            except ValueError:
                continue
        else:
            facts[field_name] = raw
    return facts


def decode(texts: list[str]) -> Decoded:
    """Decodes one message. `texts` are the bodies received for a single ref, any order."""
    first = (texts[0] if texts else "").strip()
    if HELP_RE.match(first):
        return Decoded("help")
    if m := STATUS_RE.match(first):
        return Decoded("status", tracking_id=m.group(1).upper())
    if first.startswith("SM") and "*" in first and not first.startswith(f"{VERSION}*"):
        return Decoded("unknown", reason="version")

    parsed = [parse_part(text) for text in texts]
    if any(p is None for p in parsed):
        return Decoded("unknown", reason="format")
    parts = sorted([p for p in parsed if p], key=lambda p: p.part)
    total = parts[0].total
    seen = sorted({p.part for p in parts})
    if len(seen) < total:
        return Decoded("partial", ref=parts[0].ref, received=seen, parts=total)
    payload = "".join(p.body for p in parts)
    if checksum(payload) != parts[0].crc:
        return Decoded("unknown", reason="checksum")
    return Decoded("apply", facts=decode_facts(payload), ref=parts[0].ref, parts=total)


def encode_apply(facts: dict[str, Any], ref: str = "A1") -> list[str]:
    """Mirror of the TypeScript encoder; used by tests and the SMS simulator in admin."""
    pairs = []
    reverse_gender = {v: k for k, v in GENDER.items()}
    reverse_category = {v: k for k, v in CATEGORY.items()}
    for key, name in FIELDS.items():
        value = facts.get(name)
        if value is None or value == "":
            continue
        if name == "gender":
            wire = reverse_gender.get(str(value), "")
        elif name == "social_category":
            wire = reverse_category.get(str(value), "")
        elif isinstance(value, bool):
            wire = "1" if value else "0"
        else:
            wire = str(value)
        if wire:
            pairs.append(f"{key}={wire}")
    payload = ";".join(pairs)
    crc = checksum(payload)
    room = PART_CHARS - (len(f"{VERSION}*{ref}13*{crc}*") + 1)
    chunks = [payload[i:i + room] for i in range(0, len(payload), room)] or [""]
    if len(chunks) > MAX_PARTS:
        raise ValueError(f"application does not fit in {MAX_PARTS} SMS")
    return [f"{VERSION}*{ref}{i + 1}{len(chunks)}*{chunk}*{crc}" for i, chunk in enumerate(chunks)]
