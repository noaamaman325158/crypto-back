"""Unit tests for CryptoService — CoinGecko and DB are fully mocked."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import NotFoundError
from app.models.cryptocurrency import Cryptocurrency
from app.services.crypto_service import CryptoService


def _make_coin(external_id: str = "bitcoin", rank: int = 1) -> Cryptocurrency:
    c = Cryptocurrency()
    c.id = uuid.uuid4()
    c.external_id = external_id
    c.name = external_id.capitalize()
    c.symbol = external_id[:3]
    c.current_price = 50000.0
    c.market_cap = 1_000_000_000.0
    c.price_change_percentage_24h = 2.5
    c.image_url = "https://example.com/coin.png"
    c.market_cap_rank = rank
    c.last_updated_at = datetime.now(timezone.utc)
    return c


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return CryptoService(mock_repo)


@pytest.mark.asyncio
async def test_get_all_returns_paginated(service, mock_repo):
    coins = [_make_coin("bitcoin"), _make_coin("ethereum", rank=2)]
    mock_repo.get_all.return_value = (coins, 2)

    with patch("app.services.crypto_service.cache_get", return_value=None), \
         patch("app.services.crypto_service.cache_set", new_callable=AsyncMock):
        result = await service.get_all(page=1, per_page=50, sort_by="market_cap_rank")

    assert result["total"] == 2
    assert len(result["data"]) == 2
    assert result["page"] == 1


@pytest.mark.asyncio
async def test_get_all_returns_cached(service):
    cached = {"data": [], "total": 0, "page": 1, "per_page": 50}
    with patch("app.services.crypto_service.cache_get", return_value=cached):
        result = await service.get_all(page=1, per_page=50, sort_by="market_cap_rank")
    assert result == cached


@pytest.mark.asyncio
async def test_get_by_id_not_found_raises(service, mock_repo):
    mock_repo.get_by_id.return_value = None
    with patch("app.services.crypto_service.cache_get", return_value=None):
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())


@pytest.mark.asyncio
async def test_refresh_calls_upsert_and_invalidates_cache(service, mock_repo):
    mock_markets = [{
        "id": "bitcoin", "name": "Bitcoin", "symbol": "btc",
        "current_price": 50000, "market_cap": 1e9,
        "price_change_percentage_24h": 1.0,
        "image": "https://example.com/btc.png", "market_cap_rank": 1,
    }]
    mock_repo.upsert_many.return_value = 1

    with patch.object(service.coingecko, "fetch_markets", return_value=mock_markets), \
         patch("app.services.crypto_service.cache_delete_pattern", new_callable=AsyncMock):
        count = await service.refresh()

    assert count == 1
    mock_repo.upsert_many.assert_called_once()


@pytest.mark.asyncio
async def test_get_history_parses_coingecko_response(service):
    import time
    now_ms = int(time.time() * 1000)
    raw = {"prices": [[now_ms, 50000.0], [now_ms + 86400000, 51000.0]]}

    with patch.object(service.coingecko, "fetch_history", return_value=raw), \
         patch("app.services.crypto_service.cache_get", return_value=None), \
         patch("app.services.crypto_service.cache_set", new_callable=AsyncMock):
        result = await service.get_history("bitcoin", days=7)

    assert result.coin_id == "bitcoin"
    assert len(result.prices) == 2
    assert result.prices[0].price == 50000.0
    assert result.prices[1].price == 51000.0
