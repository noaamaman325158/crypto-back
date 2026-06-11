"""
Abstract crypto data provider interface.

The application depends on this abstraction — not on CoinGecko directly.
Swapping to CoinMarketCap, Binance, or a mock for tests requires only
implementing this interface and changing the binding in get_crypto_provider().
"""

from abc import ABC, abstractmethod


class CryptoProvider(ABC):
    @abstractmethod
    async def fetch_markets(self, per_page: int = 100, page: int = 1) -> list[dict]:
        """Fetch paginated list of coins by market cap rank.

        Returns a list of dicts with keys:
            id, name, symbol, current_price, market_cap,
            price_change_percentage_24h, image, market_cap_rank
        """

    @abstractmethod
    async def fetch_history(self, coin_id: str, days: int) -> dict:
        """Fetch OHLCV price history for a coin.

        Returns {"prices": [[timestamp_ms, price], ...]}
        """

    @abstractmethod
    async def aclose(self) -> None:
        """Release underlying HTTP client resources."""
