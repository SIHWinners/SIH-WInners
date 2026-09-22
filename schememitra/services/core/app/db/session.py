import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        s = get_settings()
        if s.is_sqlite:
            path = s.database_url.split("///", 1)[-1]
            if path and path != ":memory:":
                from pathlib import Path

                Path(path).parent.mkdir(parents=True, exist_ok=True)
            _engine = create_async_engine(s.database_url, connect_args={"timeout": 30})

            @event.listens_for(_engine.sync_engine, "connect")
            def _sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        else:
            _engine = create_async_engine(s.database_url, pool_size=20, max_overflow=10, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def apply_rls_claims(session: AsyncSession, claims: dict[str, Any]) -> None:
    """On Postgres, expose the verified JWT claims to RLS policies for this transaction
    (same GUC Supabase uses). No-op on SQLite where authz is enforced in services."""
    if get_settings().is_sqlite:
        return
    await session.execute(
        text("select set_config('request.jwt.claims', :claims, true)"), {"claims": json.dumps(claims)}
    )
    if claims.get("app_role") != "admin":
        # Drop owner privileges for this transaction so RLS policies actually apply.
        await session.execute(text("set local role sm_app"))


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None
