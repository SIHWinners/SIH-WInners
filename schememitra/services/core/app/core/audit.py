"""Append-only, hash-chained audit log.

hash_n = SHA-256(prev_hash || canonical_json(entry_n)). Changing or deleting any past row
breaks every later hash, which `verify_chain` (and `python -m app.cli audit-verify`)
detects. On Postgres, a trigger additionally rejects UPDATE/DELETE on the table."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.ids import uuid7
from app.db.base import utcnow
from app.db.models import AuditLog
from app.logging import scrub

GENESIS = "0" * 64


def _canonical(actor: str, role: str, action: str, entity: str, diff: dict[str, Any], at: datetime) -> bytes:
    body = {"actor": actor, "role": role, "action": action, "entity": entity, "diff": diff,
            "at": at.isoformat()}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _hash(prev: str, payload: bytes) -> str:
    return hashlib.sha256(prev.encode() + payload).hexdigest()


async def record(
    session: AsyncSession, *, actor: str, actor_role: str, action: str, entity: str,
    diff: dict[str, Any] | None = None,
) -> AuditLog:
    """Appends one entry inside the caller's transaction.

    Appends must be serialised or two writers could chain onto the same predecessor.
    Postgres: a transaction-scoped advisory lock. SQLite: we insert first, which takes the
    database write lock, and only then read the predecessor — so no other writer can
    slip in between (a stale WAL snapshot raises instead of silently forking)."""
    if not get_settings().is_sqlite:
        await session.execute(text("select pg_advisory_xact_lock(724201)"))
    clean = scrub(diff or {})  # PII never enters the audit trail
    at = utcnow().replace(microsecond=0)
    row = AuditLog(id=uuid7(), prev_hash="", hash="", actor=actor, actor_role=actor_role, action=action,
                   entity=entity, diff=clean, at=at)
    session.add(row)
    await session.flush()
    prev = (
        await session.execute(
            select(AuditLog.hash).where(AuditLog.seq < row.seq).order_by(AuditLog.seq.desc()).limit(1)
        )
    ).scalar() or GENESIS
    row.prev_hash = prev
    row.hash = _hash(prev, _canonical(actor, actor_role, action, entity, clean, at))
    await session.flush()
    return row


@dataclass
class ChainReport:
    ok: bool
    checked: int
    broken_at_seq: int | None = None


async def verify_chain(session: AsyncSession) -> ChainReport:
    prev = GENESIS
    count = 0
    rows = await session.stream_scalars(select(AuditLog).order_by(AuditLog.seq))
    async for row in rows:
        expected = _hash(prev, _canonical(row.actor, row.actor_role, row.action, row.entity, row.diff, row.at))
        if row.prev_hash != prev or row.hash != expected:
            return ChainReport(ok=False, checked=count, broken_at_seq=row.seq)
        prev = row.hash
        count += 1
    return ChainReport(ok=True, checked=count)
