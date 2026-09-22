"""Signed QR for the loan file (spec §9.7, claim C9). The QR holds a compact Ed25519 JWS with
no personal data — tracking ID, a hash of the application content, partner and validity. A
partner officer scans it, the portal verifies the signature, then fetches the file over an
authenticated call."""

import io
import time
from typing import Any

import jwt
import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.core.keys import qr_private_key, qr_public_key
from app.errors import ProblemError

QR_TTL_SECONDS = 180 * 24 * 3600


def sign_qr(tracking_id: str, app_hash: str, partner_id: str) -> str:
    now = int(time.time())
    claims = {"tid": tracking_id, "h": app_hash[:32], "pid": partner_id, "iat": now, "exp": now + QR_TTL_SECONDS}
    return jwt.encode(claims, qr_private_key(), algorithm="EdDSA", headers={"kid": "sm-qr-1"})


def verify_qr(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token.strip(), qr_public_key(), algorithms=["EdDSA"])
    except jwt.ExpiredSignatureError as err:
        raise ProblemError(410, "QR code expired", "errors.qr_expired") from err
    except jwt.PyJWTError as err:
        raise ProblemError(400, "QR signature invalid", "errors.qr_invalid") from err


def qr_png(payload: str, box_size: int = 6) -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    out = io.BytesIO()
    qr.make_image(fill_color="#0B3D91", back_color="white").save(out, format="PNG")
    return out.getvalue()
