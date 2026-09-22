"""Cache adapter: Redis when REDIS_URL is set, otherwise an in-process TTL cache."""

import json
import time
from typing import Any, Protocol

from app.config import get_settings
from app.logging import get_logger

log = get_logger("cache")


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_s: int) -> None: ...
    async def delete_prefix(self, prefix: str) -> int: ...
    async def incr(self, key: str, ttl_s: int) -> int: ...


class MemoryCache:
    def __init__(self, max_items: int = 5000) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._max = max_items

    async def get(self, key: str) -> Any | None:
        hit = self._data.get(key)
        if not hit:
            return None
        expires, value = hit
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_s: int) -> None:
        if len(self._data) >= self._max:
            # cheap eviction: drop the entry closest to expiry
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.monotonic() + ttl_s, value)

    async def delete_prefix(self, prefix: str) -> int:
        keys = [k for k in self._data if k.startswith(prefix)]
        for k in keys:
            self._data.pop(k, None)
        return len(keys)

    async def incr(self, key: str, ttl_s: int) -> int:
        current = await self.get(key)
        value = int(current or 0) + 1
        expires = self._data[key][0] if current is not None else time.monotonic() + ttl_s
        self._data[key] = (expires, value)
        return value


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._r = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        raw = await self._r.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, ttl_s: int) -> None:
        await self._r.set(key, json.dumps(value, default=str), ex=ttl_s)

    async def delete_prefix(self, prefix: str) -> int:
        count = 0
        async for key in self._r.scan_iter(match=f"{prefix}*"):
            await self._r.delete(key)
            count += 1
        return count

    async def incr(self, key: str, ttl_s: int) -> int:
        value = await self._r.incr(key)
        if value == 1:
            await self._r.expire(key, ttl_s)
        return int(value)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        url = get_settings().redis_url
        _cache = RedisCache(url) if url else MemoryCache()
        log.info("cache backend: %s", type(_cache).__name__)
    return _cache
