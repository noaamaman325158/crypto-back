import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

MOCK_COINGECKO_MARKETS = [
    {
        "id": "bitcoin",
        "name": "Bitcoin",
        "symbol": "btc",
        "current_price": 50000.0,
        "market_cap": 1_000_000_000,
        "price_change_percentage_24h": 2.5,
        "image": "https://example.com/btc.png",
        "market_cap_rank": 1,
    },
    {
        "id": "ethereum",
        "name": "Ethereum",
        "symbol": "eth",
        "current_price": 3000.0,
        "market_cap": 500_000_000,
        "price_change_percentage_24h": 1.0,
        "image": "https://example.com/eth.png",
        "market_cap_rank": 2,
    },
]

MOCK_HISTORY = {
    "prices": [
        [1700000000000, 45000.0],
        [1700086400000, 46000.0],
        [1700172800000, 47000.0],
    ]
}


async def _seed_coins(client: AsyncClient) -> list[dict]:
    """Helper: refresh coins and return the list."""
    from app.config import settings
    with patch(
        "app.services.crypto_service.CoinGeckoClient.fetch_markets",
        new_callable=AsyncMock,
        return_value=MOCK_COINGECKO_MARKETS,
    ):
        await client.post(
            "/api/v1/cryptocurrencies/refresh",
            headers={"X-API-Key": settings.internal_api_key},
        )
    resp = await client.get("/api/v1/cryptocurrencies")
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_list_cryptocurrencies_empty(client: AsyncClient):
    resp = await client.get("/api/v1/cryptocurrencies")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_refresh_without_api_key(client: AsyncClient):
    resp = await client.post("/api/v1/cryptocurrencies/refresh")
    assert resp.status_code == 422  # Missing X-API-Key header


@pytest.mark.asyncio
async def test_refresh_with_wrong_api_key(client: AsyncClient):
    resp = await client.post(
        "/api/v1/cryptocurrencies/refresh",
        headers={"X-API-Key": "wrong-key"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_and_list(client: AsyncClient):
    from app.config import settings
    with patch(
        "app.services.crypto_service.CoinGeckoClient.fetch_markets",
        new_callable=AsyncMock,
        return_value=MOCK_COINGECKO_MARKETS,
    ):
        resp = await client.post(
            "/api/v1/cryptocurrencies/refresh",
            headers={"X-API-Key": settings.internal_api_key},
        )
    assert resp.status_code == 200
    assert resp.json()["updated"] > 0

    resp = await client.get("/api/v1/cryptocurrencies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    symbols = [c["symbol"] for c in data["data"]]
    assert "btc" in symbols


@pytest.mark.asyncio
async def test_get_coin_detail(client: AsyncClient):
    """GET /cryptocurrencies/:id returns correct coin fields."""
    coins = await _seed_coins(client)
    coin_id = coins[0]["id"]

    resp = await client.get(f"/api/v1/cryptocurrencies/{coin_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == coin_id
    assert "symbol" in data
    assert "current_price" in data
    assert "market_cap" in data
    assert "price_change_percentage_24h" in data
    assert "last_updated_at" in data


@pytest.mark.asyncio
async def test_get_nonexistent_coin_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/cryptocurrencies/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_pagination(client: AsyncClient):
    """Pagination params are respected."""
    await _seed_coins(client)

    resp_page1 = await client.get("/api/v1/cryptocurrencies?page=1&per_page=1")
    assert resp_page1.status_code == 200
    data = resp_page1.json()
    assert len(data["data"]) == 1
    assert data["page"] == 1
    assert data["per_page"] == 1
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_sorting(client: AsyncClient):
    """Coins can be sorted by market_cap_rank."""
    await _seed_coins(client)

    resp = await client.get("/api/v1/cryptocurrencies?sort_by=market_cap_rank&per_page=10")
    assert resp.status_code == 200
    coins = resp.json()["data"]
    if len(coins) >= 2:
        ranks = [c["market_cap_rank"] for c in coins if c["market_cap_rank"] is not None]
        assert ranks == sorted(ranks)


@pytest.mark.asyncio
async def test_price_history(client: AsyncClient):
    """GET /cryptocurrencies/:id/history returns price array."""
    coins = await _seed_coins(client)
    external_id = coins[0]["external_id"]

    with patch(
        "app.services.crypto_service.CoinGeckoClient.fetch_history",
        new_callable=AsyncMock,
        return_value=MOCK_HISTORY,
    ):
        resp = await client.get(f"/api/v1/cryptocurrencies/{external_id}/history?days=7")

    assert resp.status_code == 200
    data = resp.json()
    assert data["coin_id"] == external_id
    assert data["days"] == 7
    assert isinstance(data["prices"], list)
    assert len(data["prices"]) == 3
    # Each price point has timestamp and price
    assert "timestamp" in data["prices"][0]
    assert "price" in data["prices"][0]
    assert data["prices"][0]["price"] == 45000.0


@pytest.mark.asyncio
async def test_price_history_invalid_days(client: AsyncClient):
    """Only 7, 30, 90 days are accepted — other values return 422."""
    coins = await _seed_coins(client)
    external_id = coins[0]["external_id"]

    resp = await client.get(f"/api/v1/cryptocurrencies/{external_id}/history?days=999")
    assert resp.status_code == 422
