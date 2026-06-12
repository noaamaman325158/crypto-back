import uuid
from datetime import datetime, timedelta, timezone
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


async def _seed_coins(client: AsyncClient) -> list[dict]:
    """Trigger a refresh (mocking the provider) and return the coin list."""
    from app.config import settings
    with patch(
        "app.providers.coingecko.CoinGeckoProvider.fetch_markets",
        new_callable=AsyncMock,
        return_value=MOCK_COINGECKO_MARKETS,
    ):
        await client.post(
            "/api/v1/cryptocurrencies/refresh",
            headers={"X-API-Key": settings.internal_api_key},
        )
    resp = await client.get("/api/v1/cryptocurrencies")
    return resp.json()["data"]


async def _seed_price_history(external_id: str, days: int = 7) -> None:
    """Insert PriceHistory rows directly so history endpoint has data to serve."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.models.price_history import PriceHistory

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as db:
        for i in range(days):
            db.add(PriceHistory(
                external_id=external_id,
                price=45000.0 + i * 1000,
                recorded_at=now - timedelta(days=days - i),
            ))
        await db.commit()
    await engine.dispose()


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
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_with_wrong_api_key(client: AsyncClient):
    resp = await client.post(
        "/api/v1/cryptocurrencies/refresh",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_and_list(client: AsyncClient):
    from app.config import settings
    with patch(
        "app.providers.coingecko.CoinGeckoProvider.fetch_markets",
        new_callable=AsyncMock,
        return_value=MOCK_COINGECKO_MARKETS,
    ):
        resp = await client.post(
            "/api/v1/cryptocurrencies/refresh",
            headers={"X-API-Key": settings.internal_api_key},
        )
    assert resp.status_code == 202

    resp = await client.get("/api/v1/cryptocurrencies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    symbols = [c["symbol"] for c in data["data"]]
    assert "btc" in symbols


@pytest.mark.asyncio
async def test_get_coin_detail(client: AsyncClient):
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
    await _seed_coins(client)

    resp = await client.get("/api/v1/cryptocurrencies?page=1&per_page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 1
    assert data["page"] == 1
    assert data["per_page"] == 1
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_sorting(client: AsyncClient):
    await _seed_coins(client)

    resp = await client.get("/api/v1/cryptocurrencies?sort_by=market_cap_rank&per_page=10")
    assert resp.status_code == 200
    coins = resp.json()["data"]
    if len(coins) >= 2:
        ranks = [c["market_cap_rank"] for c in coins if c["market_cap_rank"] is not None]
        assert ranks == sorted(ranks)


@pytest.mark.asyncio
async def test_price_history(client: AsyncClient):
    """GET /:external_id/history returns rows from PriceHistory table (no CoinGecko call)."""
    coins = await _seed_coins(client)
    external_id = coins[0]["external_id"]
    await _seed_price_history(external_id, days=7)

    resp = await client.get(f"/api/v1/cryptocurrencies/{external_id}/history?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["coin_id"] == external_id
    assert data["days"] == 7
    assert isinstance(data["prices"], list)
    assert len(data["prices"]) >= 1
    assert "timestamp" in data["prices"][0]
    assert "price" in data["prices"][0]


@pytest.mark.asyncio
async def test_price_history_invalid_days(client: AsyncClient):
    """Only 7, 30, 90 days are accepted — other values return 422."""
    coins = await _seed_coins(client)
    external_id = coins[0]["external_id"]

    resp = await client.get(f"/api/v1/cryptocurrencies/{external_id}/history?days=999")
    assert resp.status_code == 422
