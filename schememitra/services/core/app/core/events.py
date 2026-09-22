"""Status events to the gateway's WebSocket hub. Fire-and-forget with a short timeout: a push
that cannot be delivered never blocks or fails the business transaction (SMS and the timeline
remain the record)."""

import asyncio
from typing import Any

import httpx
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging import get_logger

log = get_logger("events")
_tasks: set[asyncio.Task[Any]] = set()


async def _post(channel: str, event: str, data: dict[str, Any]) -> None:
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            await client.post(f"{s.gateway_internal_url}/internal/events",
                              json={"channel": channel, "event": event, "data": data},
                              headers={"x-internal-secret": s.internal_shared_secret})
    except httpx.HTTPError:
        log.info("event push skipped (gateway unreachable): %s", event)


def publish(channel: str, event: str, data: dict[str, Any], session: AsyncSession | None = None) -> None:
    """With `session`, the event waits for that transaction to commit (and is dropped on rollback),
    so a client that refetches on the push never reads the old state."""
    if session is not None:
        session.sync_session.info.setdefault(PENDING, []).append((channel, event, data))
        return
    if get_settings().env == "test":
        return
    task = asyncio.get_running_loop().create_task(_post(channel, event, data))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


PENDING = "sm_pending_events"


@sa_event.listens_for(Session, "after_commit")
def _flush_after_commit(sync_session: Session) -> None:
    for channel, name, data in sync_session.info.pop(PENDING, []):
        publish(channel, name, data)


@sa_event.listens_for(Session, "after_rollback")
def _drop_after_rollback(sync_session: Session) -> None:
    sync_session.info.pop(PENDING, None)


def pending(session: AsyncSession) -> list[tuple[str, str, dict[str, Any]]]:
    """Events queued on this session (tests use this; the gateway is not running there)."""
    return list(session.sync_session.info.get(PENDING, []))
