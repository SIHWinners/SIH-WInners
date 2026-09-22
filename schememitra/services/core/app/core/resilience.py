"""Timeouts, retries with jittered backoff, and circuit breakers for every external call.

`guarded(name, primary, fallback)` is the one helper adapters use: it runs `primary`
under a breaker + timeout + retry, and on failure (or when the admin chaos toggle for
`name` is on) returns `fallback()` and records which path served the request."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from app.logging import get_logger

T = TypeVar("T")
log = get_logger("resilience")


class ChaosFailure(RuntimeError):
    """Raised when an admin chaos toggle simulates a dependency outage."""


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    reset_after_s: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    last_error: str | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if time.monotonic() - self.opened_at >= self.reset_after_s:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self.last_error = None

    def record_failure(self, err: BaseException) -> None:
        self.failures += 1
        self.last_error = type(err).__name__
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


@dataclass
class _Registry:
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    chaos: set[str] = field(default_factory=set)
    last_path: dict[str, str] = field(default_factory=dict)

    def breaker(self, name: str) -> CircuitBreaker:
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name)
        return self.breakers[name]


registry = _Registry()


def set_chaos(name: str, enabled: bool) -> None:
    (registry.chaos.add if enabled else registry.chaos.discard)(name)


def is_chaos(name: str) -> bool:
    return name in registry.chaos


async def with_retry[T](
    fn: Callable[[], Awaitable[T]], *, attempts: int = 2, timeout_s: float = 4.0, base_delay_s: float = 0.2
) -> T:
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout_s)
        except (TimeoutError, OSError, ConnectionError, ValueError, RuntimeError) as err:
            last = err
            if attempt + 1 < attempts:
                # exponential backoff with full jitter
                await asyncio.sleep(random.uniform(0, base_delay_s * (2**attempt)))
    assert last is not None
    raise last


async def guarded[T](
    name: str,
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]],
    *,
    timeout_s: float = 4.0,
    attempts: int = 2,
) -> tuple[T, str]:
    """Returns (result, path) where path is "primary" or "fallback"."""
    breaker = registry.breaker(name)
    try:
        if is_chaos(name):
            raise ChaosFailure(f"chaos toggle on for {name}")
        if not breaker.allow():
            raise RuntimeError(f"circuit open for {name}")
        result = await with_retry(primary, attempts=attempts, timeout_s=timeout_s)
        breaker.record_success()
        registry.last_path[name] = "primary"
        return result, "primary"
    except Exception as err:  # noqa: BLE001 - any failure routes to the fallback
        if not isinstance(err, ChaosFailure):
            breaker.record_failure(err)
        log.warning("dependency %s failed (%s); using fallback", name, type(err).__name__)
        registry.last_path[name] = "fallback"
        return await fallback(), "fallback"
