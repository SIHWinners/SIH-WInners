"""Aadhaar handling: Verhoeff checksum validation, keep last 4 digits + salted hash only, and
black out the first eight digits on the stored image (spec §9.2, §11)."""

import io
import re

from PIL import Image, ImageDraw

from app.core.crypto import keyed_hash

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
AADHAAR_RE = re.compile(r"(?<!\d)([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})(?!\d)")


def verhoeff_check(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_digit(partial: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(partial)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def is_valid_aadhaar(number: str) -> bool:
    digits = re.sub(r"\D", "", number)
    return len(digits) == 12 and digits[0] not in "01" and verhoeff_check(digits)


def find_aadhaar(text: str) -> str | None:
    for match in AADHAAR_RE.finditer(text):
        digits = "".join(match.groups())
        if is_valid_aadhaar(digits):
            return digits
    return None


def protect(number: str) -> dict[str, str]:
    """What we keep: last four digits and a keyed hash for duplicate detection. Never the number."""
    digits = re.sub(r"\D", "", number)
    return {"aadhaar_last4": digits[-4:], "aadhaar_hash": keyed_hash(digits, "aadhaar")}


def mask_digits(image_bytes: str | bytes, boxes: list[tuple[int, int, int, int]]) -> bytes:
    """Black boxes over the regions holding the first eight digits (from OCR geometry)."""
    img = Image.open(io.BytesIO(image_bytes if isinstance(image_bytes, bytes) else image_bytes.encode())).convert("RGB")
    draw = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in boxes:
        draw.rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), fill=(0, 0, 0))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82)
    return out.getvalue()
