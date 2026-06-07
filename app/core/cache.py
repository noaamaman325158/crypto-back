import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None


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


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
