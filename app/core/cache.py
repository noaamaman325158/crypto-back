import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import redis.asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None

T = TypeVar("T")


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    value = await r.get(key)
    if value is None:
        return None
    return json.loads(value)


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value))


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    keys = await r.keys(pattern)
    if keys:
        await r.delete(*keys)


async def cache_get_or_set(
    key: str,
    factory: Callable[[], Awaitable[T]],
    ttl: int = 60,
    lock_timeout: int = 10,
) -> T:
    """Stampede-safe cache read.

    If the key is missing, only one coroutine acquires a Redis lock and calls
    factory(). All other concurrent callers wait and then read the value the
    winner populated, so the DB / external API is hit exactly once per cache miss
    regardless of how many requests arrive simultaneously.
    """
    cached = await cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    r = await get_redis()
    lock_key = f"lock:{key}"

    # Try to acquire the lock (SET NX PX)
    acquired = await r.set(lock_key, "1", nx=True, px=lock_timeout * 1000)

    if acquired:
        try:
            # Double-check in case another process populated it while we waited
            cached = await cache_get(key)
            if cached is not None:
                return cached  # type: ignore[return-value]
            value = await factory()
            await cache_set(key, value, ttl=ttl)
            return value
        finally:
            await r.delete(lock_key)
    else:
        # Wait for the lock holder to populate the cache
        for _ in range(lock_timeout * 10):
            await asyncio.sleep(0.1)
            cached = await cache_get(key)
            if cached is not None:
                return cached  # type: ignore[return-value]
        # Lock holder timed out — fall through and compute ourselves
        value = await factory()
        await cache_set(key, value, ttl=ttl)
        return value


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
