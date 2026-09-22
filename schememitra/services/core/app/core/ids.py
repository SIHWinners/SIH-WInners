"""Identifiers: UUIDv7 primary keys and human-friendly tracking IDs.

Tracking ID format: SM-<STATE>-<YY>-<6 chars><check>, e.g. SM-GJ-26-K7Q2MX9.
The alphabet is Crockford-style base32 (no I, L, O, U) so it survives being read out on
a phone call. The check character is Luhn mod N over the whole ID body, which catches
every single-character typo and most adjacent swaps on SMS/IVR lookups."""

import os
import secrets
import time
import uuid

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # 32 symbols
_N = len(ALPHABET)
_INDEX = {c: i for i, c in enumerate(ALPHABET)}


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit unix ms timestamp + random. Sorts by creation time,
    which keeps B-tree inserts cheap."""
    ts_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ts_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= (rand >> 68) & 0xFFF  # 12 bits rand_a
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # 62 bits rand_b
    return uuid.UUID(int=value)


def _code_points(body: str) -> list[int]:
    # Only alphabet characters take part; separators and the prefix letters outside the
    # alphabet are skipped so formatting never changes the check.
    return [_INDEX[c] for c in body if c in _INDEX]


def luhn_mod_n_check_char(body: str) -> str:
    factor = 2
    total = 0
    for cp in reversed(_code_points(body)):
        addend = factor * cp
        factor = 1 if factor == 2 else 2
        total += addend // _N + addend % _N
    remainder = total % _N
    return ALPHABET[(_N - remainder) % _N]


def is_valid_luhn_mod_n(full: str) -> bool:
    factor = 1
    total = 0
    for cp in reversed(_code_points(full)):
        addend = factor * cp
        factor = 1 if factor == 2 else 2
        total += addend // _N + addend % _N
    return total % _N == 0


def new_tracking_id(state_code: str, year: int | None = None) -> str:
    yy = (year or time.gmtime().tm_year) % 100
    rand = "".join(secrets.choice(ALPHABET) for _ in range(6))
    body = f"SM-{state_code.upper()}-{yy:02d}-{rand}"
    return body + luhn_mod_n_check_char(body)


def normalize_tracking_id(raw: str) -> str:
    """Accept what people actually type: lowercase, spaces, O for 0, I/L for 1."""
    cleaned = raw.strip().upper().replace(" ", "")
    head, _, tail = cleaned.rpartition("-")
    tail = tail.replace("O", "0").replace("I", "1").replace("L", "1").replace("U", "V")
    return f"{head}-{tail}" if head else tail


def is_valid_tracking_id(raw: str) -> bool:
    tid = normalize_tracking_id(raw)
    parts = tid.split("-")
    if len(parts) != 4 or parts[0] != "SM" or len(parts[1]) != 2 or len(parts[3]) != 7:
        return False
    if not parts[2].isdigit() or any(c not in _INDEX for c in parts[3]):
        return False
    return is_valid_luhn_mod_n(tid)
