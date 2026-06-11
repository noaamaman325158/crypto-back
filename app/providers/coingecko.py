import time

import httpx

from app.config import settings
from app.core.circuit_breaker import coingecko_breaker
from app.core.exceptions import ExternalServiceError, NotFoundError
from app.core.logging import get_logger
from app.core.metrics import coingecko_errors, coingecko_latency, coingecko_requests
from app.providers.base import CryptoProvider

logger = get_logger(__name__)


class CoinGeckoProvider(CryptoProvider):
    BASE_URL = settings.coingecko_base_url

    def __init__(self) -> None:
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
            data = resp.json()
            logger.info("coingecko_request", operation="markets", duration_ms=duration_ms, count=len(data))
            return data
        except httpx.HTTPStatusError as e:
            coingecko_errors.labels(operation="markets", status_code=str(e.response.status_code)).inc()
            logger.error("coingecko_error", operation="markets", status_code=e.response.status_code)
            raise ExternalServiceError(f"CoinGecko error: {e}")
        except httpx.HTTPError as e:
            coingecko_errors.labels(operation="markets", status_code="network").inc()
            logger.error("coingecko_network_error", operation="markets", error=str(e))
            raise ExternalServiceError(f"CoinGecko network error: {e}")
        finally:
            coingecko_latency.labels(operation="markets").observe(time.perf_counter() - t0)

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
            raise ExternalServiceError(f"CoinGecko network error: {e}")
        finally:
            coingecko_latency.labels(operation="history").observe(time.perf_counter() - t0)

    async def aclose(self) -> None:
        await self._client.aclose()


def get_crypto_provider() -> CryptoProvider:
    """FastAPI dependency — returns the active provider implementation.

    To swap providers (e.g. CoinMarketCap), change this one function.
    All service code depends on CryptoProvider, not CoinGeckoProvider.
    """
    return CoinGeckoProvider()
