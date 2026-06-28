from datetime import datetime, timezone

from app.core.cache import cache_delete_pattern, cache_get, cache_get_or_set
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.metrics import (
    cache_hits,
    cache_misses,
    coin_refresh_total,
    coins_updated,
)
from app.providers.base import CryptoProvider
from app.repositories.crypto_repo import CryptoRepository
from app.repositories.price_history_repo import PriceHistoryRepository
from app.schemas.cryptocurrency import HistoryResponse, PricePoint

logger = get_logger(__name__)


class CryptoService:
    def __init__(self, repo: CryptoRepository, provider: CryptoProvider | None = None) -> None:
        self.repo = repo
        # provider is only needed by refresh() (the write path). Read endpoints
        # pass provider=None so they don't construct an httpx client they never
        # use (and never close) — avoiding connection/fd leaks under load.
        self.provider = provider

    async def get_all(self, page: int, per_page: int, sort_by: str):
        cache_key = f"coins:list:{page}:{per_page}:{sort_by}"

        async def _fetch():
            cache_misses.labels(cache_key_prefix="coins:list").inc()
            logger.debug("cache_miss", key=cache_key)
            coins, total = await self.repo.get_all(page=page, per_page=per_page, sort_by=sort_by)
            return {
                "data": [_coin_to_dict(c) for c in coins],
                "total": total,
                "page": page,
                "per_page": per_page,
            }

        cached = await cache_get(cache_key)
        if cached:
            cache_hits.labels(cache_key_prefix="coins:list").inc()
            logger.debug("cache_hit", key=cache_key)
            return cached

        return await cache_get_or_set(cache_key, _fetch, ttl=60)

    async def get_by_id(self, crypto_id):
        cache_key = f"coins:detail:{crypto_id}"

        async def _fetch():
            cache_misses.labels(cache_key_prefix="coins:detail").inc()
            logger.debug("cache_miss", key=cache_key)
            coin = await self.repo.get_by_id(crypto_id)
            if not coin:
                raise NotFoundError("Cryptocurrency not found")
            return _coin_to_dict(coin)

        cached = await cache_get(cache_key)
        if cached:
            cache_hits.labels(cache_key_prefix="coins:detail").inc()
            logger.debug("cache_hit", key=cache_key)
            return cached

        return await cache_get_or_set(cache_key, _fetch, ttl=60)

    async def refresh(self) -> int:
        """On-demand refresh triggered via the internal API endpoint.
        In the push model this is a privileged escape hatch, not the primary path."""
        if self.provider is None:
            raise RuntimeError("CryptoService.refresh() requires a provider")
        coin_refresh_total.inc()
        logger.info("coin_refresh_started")
        raw = await self.provider.fetch_markets(per_page=100)
        coins = [
            {
                "external_id": c["id"],
                "name": c["name"],
                "symbol": c["symbol"],
                "current_price": c.get("current_price"),
                "market_cap": c.get("market_cap"),
                "price_change_percentage_24h": c.get("price_change_percentage_24h"),
                "image_url": c.get("image"),
                "market_cap_rank": c.get("market_cap_rank"),
                "last_refreshed_at": datetime.now(timezone.utc),
            }
            for c in raw
        ]
        count = await self.repo.upsert_many(coins)
        coins_updated.inc(count)
        # Invalidate every derived cache so the next read reflects fresh data.
        # detail keys are write-through-populated by the worker, but an on-demand
        # refresh changes the underlying rows, so stale detail entries must go too.
        await cache_delete_pattern("coins:list:*")
        await cache_delete_pattern("coins:detail:*")
        await cache_delete_pattern("coins:top_movers:*")
        logger.info("coin_refresh_completed", count=count)
        return count

    async def get_history(self, external_id: str, days: int) -> HistoryResponse:
        """Serves price history from PostgreSQL (populated by the scheduled worker).
        No CoinGecko call at request time."""
        cache_key = f"coins:history:{external_id}:{days}"

        async def _fetch():
            cache_misses.labels(cache_key_prefix="coins:history").inc()
            logger.debug("cache_miss", key=cache_key)
            rows = await PriceHistoryRepository(self.repo.db).get_history(external_id, days)
            if not rows:
                raise NotFoundError(
                    f"No price history for '{external_id}'. "
                    "Data may not have been collected yet — check back after the next refresh cycle."
                )
            prices = [PricePoint(timestamp=r.recorded_at, price=r.price) for r in rows]
            result = HistoryResponse(coin_id=external_id, days=days, prices=prices)
            return result.model_dump(mode="json")

        cached = await cache_get(cache_key)
        if cached:
            cache_hits.labels(cache_key_prefix="coins:history").inc()
            logger.debug("cache_hit", key=cache_key)
            return HistoryResponse(**cached)

        raw_result = await cache_get_or_set(cache_key, _fetch, ttl=300)
        return HistoryResponse(**raw_result)

    async def get_top_movers(self, limit: int = 5):
        """Returns top gainers and losers by 24h price change from DB."""
        cache_key = f"coins:top_movers:{limit}"

        async def _fetch():
            cache_misses.labels(cache_key_prefix="coins:top_movers").inc()
            gainers, losers = await self.repo.get_top_movers(limit=limit)
            return {
                "gainers": [_coin_to_dict(c) for c in gainers],
                "losers": [_coin_to_dict(c) for c in losers],
            }

        cached = await cache_get(cache_key)
        if cached:
            cache_hits.labels(cache_key_prefix="coins:top_movers").inc()
            return cached

        return await cache_get_or_set(cache_key, _fetch, ttl=60)


def _coin_to_dict(coin) -> dict:
    last_refreshed = getattr(coin, "last_refreshed_at", None)
    age = (
        int((datetime.now(timezone.utc) - last_refreshed).total_seconds())
        if last_refreshed
        else None
    )
    return {
        "id": str(coin.id),
        "external_id": coin.external_id,
        "name": coin.name,
        "symbol": coin.symbol,
        "current_price": coin.current_price,
        "market_cap": coin.market_cap,
        "price_change_percentage_24h": coin.price_change_percentage_24h,
        "image_url": coin.image_url,
        "market_cap_rank": coin.market_cap_rank,
        "last_updated_at": coin.last_updated_at.isoformat() if coin.last_updated_at else None,
        "data_age_seconds": age,
    }
