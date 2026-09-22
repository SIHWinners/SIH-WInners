"""Object storage adapter. Every blob is AES-256-GCM encrypted by the app before it is
written, so the local folder and the S3 bucket only ever hold ciphertext (on S3 we also
request SSE as a second layer)."""

import asyncio
import os
import time
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.core.crypto import decrypt_bytes, encrypt_bytes


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...


def _safe_key(key: str) -> str:
    if ".." in key or key.startswith(("/", "\\")):
        raise ValueError("invalid storage key")
    return key


class LocalEncryptedStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = encrypt_bytes(data, aad=key.encode())

        def write_atomically() -> None:
            # Readers must never see a half-written blob (e.g. a PDF still being rendered).
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{id(blob)}.tmp")
            tmp.write_bytes(blob)
            # Windows refuses to replace a file another request is reading; that read lasts
            # milliseconds, so retry briefly instead of failing the write.
            for attempt in range(20):
                try:
                    os.replace(tmp, path)
                    return
                except PermissionError:
                    if attempt == 19:
                        tmp.unlink(missing_ok=True)
                        raise
                    time.sleep(0.05)

        await asyncio.to_thread(write_atomically)

    async def get(self, key: str) -> bytes:
        blob = await asyncio.to_thread(self._path(key).read_bytes)
        return decrypt_bytes(blob, aad=key.encode())

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3EncryptedStorage:
    def __init__(self) -> None:
        import boto3  # optional extra: `uv sync --extra s3`

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3", endpoint_url=s.s3_endpoint, aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
        )

    async def put(self, key: str, data: bytes) -> None:
        blob = encrypt_bytes(data, aad=key.encode())
        await asyncio.to_thread(
            self.client.put_object, Bucket=self.bucket, Key=_safe_key(key), Body=blob,
            ServerSideEncryption="AES256",
        )

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=_safe_key(key))
        return decrypt_bytes(obj["Body"].read(), aad=key.encode())

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=_safe_key(key))

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=_safe_key(key))
            return True
        except Exception:  # noqa: BLE001
            return False


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3EncryptedStorage() if s.storage_mode == "s3" else LocalEncryptedStorage(s.storage_dir)
    return _storage
