"""
Idempotency support for mutating endpoints.

Clients send an `Idempotency-Key: <uuid>` header. If we've seen that key
within the TTL window, we return the stored response verbatim without
re-executing the handler. This makes retries safe for POST endpoints.

Usage (in an endpoint):
    from app.core.idempotency import idempotency_key_header, check_idempotency, store_idempotency

    async def my_endpoint(request: Request, idempotency_key: str | None = idempotency_key_header):
        cached = await check_idempotency(idempotency_key)
        if cached:
            return cached
        result = await do_work()
        await store_idempotency(idempotency_key, result)
        return result
"""

import json
from typing import Any

from fastapi import Header

from app.core.cache import cache_get, cache_set
from app.core.logging import get_logger

logger = get_logger(__name__)

_TTL = 86400  # 24 hours


def idempotency_key_header(idempotency_key: str | None = Header(default=None)) -> str | None:
    return idempotency_key


async def check_idempotency(key: str | None) -> Any | None:
    if not key:
        return None
    cache_key = f"idempotency:{key}"
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("idempotency_hit", key=key)
    return cached


async def store_idempotency(key: str | None, value: Any, ttl: int = _TTL) -> None:
    if not key:
        return
    cache_key = f"idempotency:{key}"
    serializable = value if isinstance(value, dict) else json.loads(json.dumps(value, default=str))
    await cache_set(cache_key, serializable, ttl=ttl)
