"""
Scheduled coin refresh worker.

Runs as a separate process from the FastAPI app. Fetches CoinGecko market data
in paginated batches, upserts into PostgreSQL, appends a PriceHistory snapshot,
then write-through populates Redis so the API layer never needs to call CoinGecko.

Architecture:
  CoinGecko → [this worker] → PostgreSQL (system of record)
                           → Redis  (write-through cache, TTL=300s)
  FastAPI reads from Redis → PostgreSQL only (no CoinGecko calls at request time)
"""

import asyncio
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.cache import cache_delete_pattern, cache_set
from app.core.logging import get_logger, setup_logging
from app.core.metrics import (
    coin_refresh_total,
    coins_updated,
    data_age_seconds,
    refresh_coins_updated_last_run,
    refresh_duration_seconds,
    refresh_failures_total,
    refresh_last_success_timestamp,
)
from app.models import cryptocurrency, price_history  # noqa: F401 — ensure tables are registered
from app.providers.coingecko import CoinGeckoProvider
from app.repositories.crypto_repo import CryptoRepository
from app.repositories.price_history_repo import PriceHistoryRepository

setup_logging()
logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

REFRESH_INTERVAL_SECONDS = 300   # 5-minute cadence
COINS_PER_PAGE = 250             # CoinGecko max per_page
TOTAL_PAGES = 2                  # 500 coins total; adjust as needed
MAX_RETRIES = 3
CACHE_TTL = 310                  # slightly longer than refresh interval
DISTRIBUTED_LOCK_TTL_MS = 270_000  # 4.5 min — prevents overlap on slow runs

# ── DB / Redis setup (module-level, shared across scheduler invocations) ──────

_engine = create_async_engine(settings.database_url, pool_size=3, max_overflow=2)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


# ── Core refresh logic ────────────────────────────────────────────────────────

async def _fetch_and_store_page(
    page: int,
    provider: CoinGeckoProvider,
    db: AsyncSession,
    redis: aioredis.Redis,
    now: datetime,
) -> int:
    """Fetch one page from CoinGecko, upsert DB, write-through Redis. Returns coins saved."""
    repo = CryptoRepository(db)
    hist_repo = PriceHistoryRepository(db)

    raw = await provider.fetch_markets(per_page=COINS_PER_PAGE, page=page)
    if not raw:
        return 0

    coins = []
    for c in raw:
        coins.append({
            "external_id": c["id"],
            "name": c["name"],
            "symbol": c["symbol"],
            "current_price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "price_change_percentage_24h": c.get("price_change_percentage_24h"),
            "image_url": c.get("image"),
            "market_cap_rank": c.get("market_cap_rank"),
            "last_refreshed_at": now,
        })

    count = await repo.upsert_many(coins)

    # Append price snapshot for each coin with a known price
    for c in raw:
        price = c.get("current_price")
        if price is not None:
            await hist_repo.append_price_snapshot(c["id"], price, now)

    await db.commit()

    # Write-through: populate Redis with fresh values so API reads don't hit DB
    import json
    for c in raw:
        coin_dict = {
            "id": None,  # will be filled by repo on next DB read if needed
            "external_id": c["id"],
            "name": c["name"],
            "symbol": c["symbol"],
            "current_price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "price_change_percentage_24h": c.get("price_change_percentage_24h"),
            "image_url": c.get("image"),
            "market_cap_rank": c.get("market_cap_rank"),
            "last_updated_at": now.isoformat(),
            "data_age_seconds": 0,
        }
        await redis.setex(
            f"coins:detail:{c['id']}",
            CACHE_TTL,
            json.dumps(coin_dict),
        )

    # Invalidate list/top-mover caches — they'll repopulate from fresh DB data
    keys = await redis.keys("coins:list:*")
    if keys:
        await redis.delete(*keys)
    keys = await redis.keys("coins:top_movers:*")
    if keys:
        await redis.delete(*keys)

    return count


async def _run_refresh() -> None:
    """One full refresh cycle across all pages. Called by APScheduler."""
    lock_key = "worker:refresh:lock"
    redis = await _get_redis()

    acquired = await redis.set(lock_key, "1", nx=True, px=DISTRIBUTED_LOCK_TTL_MS)
    if not acquired:
        logger.info("refresh_skipped_lock_held")
        return

    try:
        start = time.monotonic()
        now = datetime.now(timezone.utc)
        coin_refresh_total.inc()
        logger.info("refresh_started", pages=TOTAL_PAGES)

        provider = CoinGeckoProvider()
        total_updated = 0

        try:
            for page in range(1, TOTAL_PAGES + 1):
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        async with _session_factory() as db:
                            count = await _fetch_and_store_page(page, provider, db, redis, now)
                            total_updated += count
                            logger.info("refresh_page_done", page=page, coins=count)
                            break
                    except Exception as exc:
                        logger.warning(
                            "refresh_page_failed",
                            page=page,
                            attempt=attempt,
                            error=str(exc),
                        )
                        if attempt == MAX_RETRIES:
                            refresh_failures_total.labels(batch_page=str(page)).inc()
                            async with _session_factory() as db:
                                from app.repositories.price_history_repo import PriceHistoryRepository
                                await PriceHistoryRepository(db).write_dead_letter(page, str(exc))
                                await db.commit()
                        else:
                            await asyncio.sleep(2 ** attempt)
        finally:
            await provider.aclose()

        elapsed = time.monotonic() - start
        refresh_last_success_timestamp.set(now.timestamp())
        refresh_coins_updated_last_run.set(total_updated)
        refresh_duration_seconds.set(elapsed)
        coins_updated.inc(total_updated)
        data_age_seconds.set(0)

        # Purge history older than 90 days (housekeeping, runs after each cycle)
        async with _session_factory() as db:
            from app.repositories.price_history_repo import PriceHistoryRepository
            purged = await PriceHistoryRepository(db).purge_old_history(keep_days=90)
            await db.commit()
            if purged:
                logger.info("history_purged", rows=purged)

        logger.info("refresh_completed", total=total_updated, duration_s=round(elapsed, 2))

    finally:
        await redis.delete(lock_key)
        await redis.aclose()


async def _tick_data_age() -> None:
    """Update the data_age_seconds gauge every 30 s based on last refresh timestamp."""
    last_ts = refresh_last_success_timestamp._value.get()  # type: ignore[attr-defined]
    if last_ts:
        age = time.time() - last_ts
        data_age_seconds.set(age)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("worker_starting", interval_s=REFRESH_INTERVAL_SECONDS)

    # Expose Prometheus metrics on :9091 (separate from the API's :8000/metrics)
    start_http_server(9091)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_refresh,
        trigger=IntervalTrigger(seconds=REFRESH_INTERVAL_SECONDS),
        id="coin_refresh",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),  # run immediately on startup
    )
    scheduler.add_job(
        _tick_data_age,
        trigger=IntervalTrigger(seconds=30),
        id="data_age_tick",
        max_instances=1,
    )
    scheduler.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("worker_stopping")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
