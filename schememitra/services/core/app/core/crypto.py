"""Field-level encryption and keyed hashing.

Envelope encryption: every value gets a fresh 256-bit data key; the data key is wrapped
with the key-encryption key (KEK) from settings/KMS. Rotating the KEK only rewraps small
data keys. Ciphertext layout (base64): v1 | wrap_nonce | wrapped_dk | nonce | ciphertext."""

import base64
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_VERSION = b"\x01"


@lru_cache
def _kek() -> bytes:
    key = base64.b64decode(get_settings().data_kek_b64)
    if len(key) != 32:
        raise ValueError("DATA_KEK_B64 must decode to exactly 32 bytes")
    return key


def encrypt_bytes(plaintext: bytes, aad: bytes = b"") -> bytes:
    data_key = AESGCM.generate_key(bit_length=256)
    wrap_nonce = os.urandom(12)
    wrapped = AESGCM(_kek()).encrypt(wrap_nonce, data_key, b"dk")
    nonce = os.urandom(12)
    ct = AESGCM(data_key).encrypt(nonce, plaintext, aad)
    return _VERSION + wrap_nonce + wrapped + nonce + ct


def decrypt_bytes(blob: bytes, aad: bytes = b"") -> bytes:
    if blob[:1] != _VERSION:
        raise ValueError("unknown ciphertext version")
    wrap_nonce = blob[1:13]
    wrapped = blob[13:61]  # 32-byte data key + 16-byte GCM tag
    nonce = blob[61:73]
    ct = blob[73:]
    data_key = AESGCM(_kek()).decrypt(wrap_nonce, wrapped, b"dk")
    return AESGCM(data_key).decrypt(nonce, ct, aad)


def encrypt_str(value: str | None) -> str | None:
    if value is None:
        return None
    return base64.b64encode(encrypt_bytes(value.encode("utf-8"))).decode("ascii")


def decrypt_str(value: str | None) -> str | None:
    if value is None:
        return None
    return decrypt_bytes(base64.b64decode(value)).decode("utf-8")


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 with the deployment salt. Used for phone lookup and Aadhaar dedup
    without storing the raw identifier. `purpose` domain-separates the hashes."""
    salt = get_settings().hash_salt.encode()
    return hmac.new(salt, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def phone_hash(phone: str) -> str:
    return keyed_hash(normalize_phone(phone), "phone")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
