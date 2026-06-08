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
    }
]


@pytest.mark.asyncio
async def test_list_cryptocurrencies_empty(client: AsyncClient):
    resp = await client.get("/api/v1/cryptocurrencies")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data


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
    with patch(
        "app.services.crypto_service.CoinGeckoClient.fetch_markets",
        new_callable=AsyncMock,
        return_value=MOCK_COINGECKO_MARKETS,
    ):
        from app.config import settings
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
    assert data["data"][0]["symbol"] == "btc"


@pytest.mark.asyncio
async def test_get_nonexistent_coin(client: AsyncClient):
    import uuid
    resp = await client.get(f"/api/v1/cryptocurrencies/{uuid.uuid4()}")
    assert resp.status_code == 404
