"""ARQ worker entrypoint for the compose profile: `arq app.worker.WorkerSettings`.

Jobs are the same coroutines the in-process queue runs locally (app.core.jobs registry), so
local and compose behave identically. Importing the modules registers their jobs."""

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.core.jobs import registered_jobs

JOB_MODULES = [
    "app.modules.documents.jobs",
    "app.modules.applications.jobs",
    "app.modules.analytics.jobs",
]


def _load_functions() -> list[Any]:
    import importlib

    for name in JOB_MODULES:
        importlib.import_module(name)
    functions = []
    for job_name, fn in registered_jobs().items():
        async def runner(ctx: dict[str, Any], _fn: Any = fn, **kwargs: Any) -> Any:
            return await _fn(**kwargs)

        runner.__qualname__ = runner.__name__ = job_name
        functions.append(runner)
    return functions


async def _purge(ctx: dict[str, Any]) -> Any:
    from app.modules.documents.jobs import purge_expired_images

    return await purge_expired_images()


async def _refresh_insights(ctx: dict[str, Any]) -> Any:
    from app.modules.analytics.jobs import refresh_aggregates

    return await refresh_aggregates()


class WorkerSettings:
    functions = _load_functions()
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")
    cron_jobs = [
        cron(_purge, minute={0, 30}),
        cron(_refresh_insights, minute={0, 15, 30, 45}),
    ]
    max_jobs = 8
    job_timeout = 120
