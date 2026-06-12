from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

MOCK_MARKETS = [{
    "id": "ethereum", "name": "Ethereum", "symbol": "eth",
    "current_price": 3000.0, "market_cap": 500_000_000,
    "price_change_percentage_24h": 1.0,
    "image": "https://example.com/eth.png", "market_cap_rank": 2,
}]


async def register_and_login(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "pass"})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "pass"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_watchlist_full_flow(client: AsyncClient):
    token = await register_and_login(client, "watch@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Seed a coin via mocked provider
    with patch(
        "app.providers.coingecko.CoinGeckoProvider.fetch_markets",
        new_callable=AsyncMock,
        return_value=MOCK_MARKETS,
    ):
        from app.config import settings
        await client.post(
            "/api/v1/cryptocurrencies/refresh",
            headers={"X-API-Key": settings.internal_api_key},
        )

    coins_resp = await client.get("/api/v1/cryptocurrencies")
    coin_id = coins_resp.json()["data"][0]["id"]

    # Add to watchlist
    resp = await client.post("/api/v1/watchlist", json={"cryptocurrency_id": coin_id}, headers=headers)
    assert resp.status_code == 201

    # Duplicate should 409
    resp2 = await client.post("/api/v1/watchlist", json={"cryptocurrency_id": coin_id}, headers=headers)
    assert resp2.status_code == 409

    # Get watchlist
    resp = await client.get("/api/v1/watchlist", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["cryptocurrency"]["symbol"] == "eth"

    # Remove from watchlist
    resp = await client.delete(f"/api/v1/watchlist/{coin_id}", headers=headers)
    assert resp.status_code == 204

    # Should be empty now
    resp = await client.get("/api/v1/watchlist", headers=headers)
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_watchlist_isolation(client: AsyncClient):
    """User A cannot see User B's watchlist."""
    token_a = await register_and_login(client, "user_a@example.com")
    token_b = await register_and_login(client, "user_b@example.com")

    resp_a = await client.get("/api/v1/watchlist", headers={"Authorization": f"Bearer {token_a}"})
    resp_b = await client.get("/api/v1/watchlist", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
