import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="sm-test-"))
os.environ.update({
    "ENV": "test",
    # TEST_DATABASE_URL points the suite at Postgres+PostGIS (compose profile); default is SQLite.
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}",
    "STORAGE_DIR": str(_TMP / "objects"),
    "QR_SIGNING_KEY_PATH": str(_TMP / "keys" / "qr.pem"),
    "LLM_MODE": "off",
    "OCR_MODE": "sandbox",
    "BHASHINI_MODE": "sandbox",
    "SMS_MODE": "console",
    "DIGILOCKER_MODE": "sandbox",
    "DEMO_MODE": "true",
    "REDIS_URL": "",
})

import httpx  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402

from app.db import models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    if os.environ["DATABASE_URL"].startswith("sqlite"):
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        # Postgres gets the real migrations (PostGIS geom, partitions, RLS), on a clean schema.
        import subprocess
        import sys

        async with get_engine().begin() as conn:
            from sqlalchemy import text

            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await get_engine().dispose()
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=os.environ.copy())
    yield


@pytest.fixture
async def session():  # type: ignore[no-untyped-def]
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture(scope="session")
async def app():  # type: ignore[no-untyped-def]
    from app.main import create_app

    application = create_app()
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def login(client: httpx.AsyncClient, phone: str) -> dict[str, str]:
    otp = (await client.post("/v1/auth/otp/request", json={"phone": phone})).json()["dev_otp"]
    token = (await client.post("/v1/auth/otp/verify", json={"phone": phone, "code": otp})).json()["access_token"]
    return {"authorization": f"Bearer {token}"}
