import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.core.cache import cache_delete_pattern, cache_get, cache_get_or_set
from app.core.circuit_breaker import coingecko_breaker
from app.core.exceptions import ExternalServiceError, NotFoundError
from app.core.logging import get_logger
from app.core.metrics import (
    cache_hits,
    cache_misses,
    coin_refresh_total,
    coingecko_errors,
    coingecko_latency,
    coingecko_requests,
    coins_updated,
)
from app.repositories.crypto_repo import CryptoRepository
from app.schemas.cryptocurrency import HistoryResponse, PricePoint

logger = get_logger(__name__)


class CoinGeckoClient:
    BASE_URL = settings.coingecko_base_url

    def __init__(self):
        headers = {"accept": "application/json"}
        if settings.coingecko_api_key:
            headers["x-cg-demo-api-key"] = settings.coingecko_api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=30.0,
        )

    async def fetch_markets(self, per_page: int = 100, page: int = 1) -> list[dict]:
        coingecko_requests.labels(operation="markets").inc()
        t0 = time.perf_counter()
        try:
            async with coingecko_breaker:
                resp = await self._client.get(
                    "/coins/markets",
                    params={
                        "vs_currency": "usd",
                        "order": "market_cap_desc",
                        "per_page": per_page,
                        "page": page,
                        "sparkline": False,
                    },
                )
                resp.raise_for_status()
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.info("coingecko_request", operation="markets", duration_ms=duration_ms, count=len(resp.json()))
            return resp.json()
        except httpx.HTTPStatusError as e:
            coingecko_errors.labels(operation="markets", status_code=str(e.response.status_code)).inc()
            logger.error("coingecko_error", operation="markets", status_code=e.response.status_code)
            raise ExternalServiceError(f"CoinGecko error: {e}")
        except httpx.HTTPError as e:
            coingecko_errors.labels(operation="markets", status_code="network").inc()
            logger.error("coingecko_network_error", operation="markets", error=str(e))
            raise ExternalServiceError(f"CoinGecko error: {e}")
        finally:
            coingecko_latency.labels(operation="markets").observe(time.perf_counter() - t0)

    async def fetch_coin_detail(self, coin_id: str) -> dict:
        coingecko_requests.labels(operation="detail").inc()
        t0 = time.perf_counter()
        try:
            async with coingecko_breaker:
                resp = await self._client.get(
                    f"/coins/{coin_id}",
                    params={"localization": False, "tickers": False, "community_data": False},
                )
                resp.raise_for_status()
            logger.info("coingecko_request", operation="detail", coin_id=coin_id, duration_ms=round((time.perf_counter() - t0) * 1000, 2))
            return resp.json()
        except httpx.HTTPStatusError as e:
            coingecko_errors.labels(operation="detail", status_code=str(e.response.status_code)).inc()
            logger.error("coingecko_error", operation="detail", coin_id=coin_id, status_code=e.response.status_code)
            if e.response.status_code == 404:
                raise NotFoundError(f"Coin '{coin_id}' not found on CoinGecko")
            raise ExternalServiceError(f"CoinGecko error: {e}")
        except httpx.HTTPError as e:
            coingecko_errors.labels(operation="detail", status_code="network").inc()
            logger.error("coingecko_network_error", operation="detail", coin_id=coin_id, error=str(e))
            raise ExternalServiceError(f"CoinGecko error: {e}")
        finally:
            coingecko_latency.labels(operation="detail").observe(time.perf_counter() - t0)

    async def fetch_history(self, coin_id: str, days: int) -> dict:
        coingecko_requests.labels(operation="history").inc()
        t0 = time.perf_counter()
        try:
            async with coingecko_breaker:
                resp = await self._client.get(
                    f"/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": days},
                )
                resp.raise_for_status()
            logger.info("coingecko_request", operation="history", coin_id=coin_id, days=days, duration_ms=round((time.perf_counter() - t0) * 1000, 2))
            return resp.json()
        except httpx.HTTPStatusError as e:
            coingecko_errors.labels(operation="history", status_code=str(e.response.status_code)).inc()
            logger.error("coingecko_error", operation="history", coin_id=coin_id, status_code=e.response.status_code)
            if e.response.status_code == 404:
                raise NotFoundError(f"Coin '{coin_id}' not found")
            raise ExternalServiceError(f"CoinGecko error: {e}")
        except httpx.HTTPError as e:
            coingecko_errors.labels(operation="history", status_code="network").inc()
            logger.error("coingecko_network_error", operation="history", coin_id=coin_id, error=str(e))
            raise ExternalServiceError(f"CoinGecko error: {e}")
        finally:
            coingecko_latency.labels(operation="history").observe(time.perf_counter() - t0)

    async def aclose(self):
        await self._client.aclose()


class CryptoService:
    def __init__(self, repo: CryptoRepository):
        self.repo = repo
        self.coingecko = CoinGeckoClient()

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

        result = await cache_get_or_set(cache_key, _fetch, ttl=60)
        return result

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
        raw = await self.coingecko.fetch_markets(per_page=100)
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
            raw = await self.coingecko.fetch_history(external_id, days)
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
