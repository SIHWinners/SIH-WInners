"""Background jobs. With Redis we enqueue to ARQ workers (`python -m app.worker`);
without it jobs run as in-process asyncio tasks. Callers get a job id either way and can
poll `/v1/jobs/{id}` — the UI shows a skeleton while waiting."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.core.ids import uuid7
from app.logging import get_logger

log = get_logger("jobs")
JobFn = Callable[..., Awaitable[Any]]
_REGISTRY: dict[str, JobFn] = {}


def job(name: str) -> Callable[[JobFn], JobFn]:
    def deco(fn: JobFn) -> JobFn:
        _REGISTRY[name] = fn
        return fn

    return deco


@dataclass
class JobState:
    id: str
    name: str
    status: str = "queued"  # queued | running | done | failed
    result: Any = None
    error: str | None = None
    _task: asyncio.Task[Any] | None = field(default=None, repr=False)


class InlineQueue:
    def __init__(self) -> None:
        self.jobs: dict[str, JobState] = {}

    async def enqueue(self, name: str, **kwargs: Any) -> JobState:
        state = JobState(id=str(uuid7()), name=name)
        self.jobs[state.id] = state

        async def run() -> None:
            state.status = "running"
            try:
                state.result = await _REGISTRY[name](**kwargs)
                state.status = "done"
            except Exception as err:  # noqa: BLE001
                log.exception("job %s failed", name)
                state.status, state.error = "failed", type(err).__name__

        state._task = asyncio.create_task(run())
        # keep only the most recent jobs in memory
        if len(self.jobs) > 1000:
            for old in list(self.jobs)[:200]:
                self.jobs.pop(old, None)
        return state

    async def get(self, job_id: str) -> JobState | None:
        return self.jobs.get(job_id)

    async def wait(self, job_id: str, timeout_s: float = 30) -> JobState | None:
        state = self.jobs.get(job_id)
        if state and state._task:
            await asyncio.wait_for(asyncio.shield(state._task), timeout_s)
        return state


class ArqQueue:
    def __init__(self, url: str) -> None:
        self.url = url
        self._pool: Any = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            self._pool = await create_pool(RedisSettings.from_dsn(self.url))
        return self._pool

    async def enqueue(self, name: str, **kwargs: Any) -> JobState:
        pool = await self._get_pool()
        j = await pool.enqueue_job(name, **kwargs)
        return JobState(id=j.job_id, name=name)

    async def get(self, job_id: str) -> JobState | None:
        from arq.jobs import Job

        pool = await self._get_pool()
        j = Job(job_id, pool)
        status = await j.status()
        state = JobState(id=job_id, name="", status=str(status.value))
        if status.value == "complete":
            info = await j.result_info()
            state.status = "done" if info and info.success else "failed"
            state.result = info.result if info else None
        return state

    async def wait(self, job_id: str, timeout_s: float = 30) -> JobState | None:
        from arq.jobs import Job

        pool = await self._get_pool()
        await Job(job_id, pool).result(timeout=timeout_s)
        return await self.get(job_id)


_queue: InlineQueue | ArqQueue | None = None


def get_queue() -> InlineQueue | ArqQueue:
    global _queue
    if _queue is None:
        url = get_settings().redis_url
        use_arq = False
        if url:
            try:
                import arq  # noqa: F401

                use_arq = True
            except ImportError:
                log.warning("REDIS_URL set but arq not installed; running jobs inline")
        _queue = ArqQueue(url) if use_arq and url else InlineQueue()
    return _queue


def registered_jobs() -> dict[str, JobFn]:
    return dict(_REGISTRY)
