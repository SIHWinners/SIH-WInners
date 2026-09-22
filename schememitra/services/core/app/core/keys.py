"""Ed25519 key for signing QR payloads. Generated on first start in dev; in production
mount the PEM from a secret store (QR_SIGNING_KEY_PATH)."""

from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.config import get_settings


def ensure_qr_signing_key() -> None:
    path = get_settings().qr_signing_key_path
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    path.write_bytes(pem)


@lru_cache
def qr_private_key() -> Ed25519PrivateKey:
    ensure_qr_signing_key()
    key = serialization.load_pem_private_key(get_settings().qr_signing_key_path.read_bytes(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return key


def qr_public_key() -> Ed25519PublicKey:
    return qr_private_key().public_key()


def qr_public_key_pem() -> str:
    return qr_public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
