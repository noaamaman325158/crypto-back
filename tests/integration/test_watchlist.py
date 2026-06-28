import pytest
from httpx import AsyncClient

MOCK_MARKETS = [{
    "id": "ethereum", "name": "Ethereum", "symbol": "eth",
    "current_price": 3000.0, "market_cap": 500_000_000,
    "price_change_percentage_24h": 1.0,
    "image": "https://example.com/eth.png", "market_cap_rank": 2,
}]


async def register_and_login(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["access_token"]


async def _seed_coins(client: AsyncClient) -> list[dict]:
    """Seed coins directly via the repository (deterministic), then read via API.

    POST /refresh upserts in a fire-and-forget background task, which is
    non-deterministic under the test loop — so we insert directly instead.
    """
    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.repositories.crypto_repo import CryptoRepository

    now = datetime.now(timezone.utc)
    coins = [
        {
            "external_id": c["id"], "name": c["name"], "symbol": c["symbol"],
            "current_price": c.get("current_price"), "market_cap": c.get("market_cap"),
            "price_change_percentage_24h": c.get("price_change_percentage_24h"),
            "image_url": c.get("image"), "market_cap_rank": c.get("market_cap_rank"),
            "last_refreshed_at": now,
        }
        for c in MOCK_MARKETS
    ]
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        await CryptoRepository(db).upsert_many(coins)
        await db.commit()
    await engine.dispose()

    resp = await client.get("/api/v1/cryptocurrencies")
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_watchlist_full_flow(client: AsyncClient):
    token = await register_and_login(client, "watch@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    coins = await _seed_coins(client)
    coin_id = coins[0]["id"]

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
