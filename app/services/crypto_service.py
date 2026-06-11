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
from app.schemas.cryptocurrency import HistoryResponse, PricePoint

logger = get_logger(__name__)


class CryptoService:
    def __init__(self, repo: CryptoRepository, provider: CryptoProvider) -> None:
        self.repo = repo
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
            }
            for c in raw
        ]
        count = await self.repo.upsert_many(coins)
        coins_updated.inc(count)
        await cache_delete_pattern("coins:list:*")
        logger.info("coin_refresh_completed", count=count)
        return count

    async def get_history(self, external_id: str, days: int) -> HistoryResponse:
        cache_key = f"coins:history:{external_id}:{days}"

        async def _fetch():
            cache_misses.labels(cache_key_prefix="coins:history").inc()
            logger.debug("cache_miss", key=cache_key)
            raw = await self.provider.fetch_history(external_id, days)
            prices = [
                PricePoint(
                    timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                    price=price,
                )
                for ts, price in raw.get("prices", [])
            ]
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
    }
