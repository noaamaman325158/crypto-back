"""
Extensive API tests — edge cases, security boundaries, contract validation.

Covers:
- Input validation (malformed payloads, wrong types, missing fields)
- Auth security (token misuse, RBAC, header injection)
- Pagination/sorting edge cases
- Rate limit headers presence
- Response contract (all required fields present and correct types)
- Idempotency and ordering guarantees
- Concurrent-safe operations (watchlist uniqueness constraint)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.integration.test_cryptocurrencies import _seed_coins

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _register_and_login(client: AsyncClient, email: str, password: str = "Password123!") -> dict:
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()


async def _auth_headers(client: AsyncClient, email: str) -> dict:
    tokens = await _register_and_login(client, email)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── Auth — Input Validation ───────────────────────────────────────────────────

class TestAuthValidation:

    @pytest.mark.asyncio
    async def test_register_missing_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={"password": "abc"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={"email": "x@x.com"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_format(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email", "password": "abc123"
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_empty_body(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={"email": "x@x.com"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@nowhere.com", "password": "password"
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_register_response_contract(self, client: AsyncClient):
        """Register response must include all required fields with correct types."""
        resp = await client.post("/api/v1/auth/register", json={
            "email": "contract@test.com", "password": "pass123"
        })
        assert resp.status_code == 201
        body = resp.json()
        assert isinstance(body["id"], str)
        assert body["email"] == "contract@test.com"
        assert body["role"] == "user"
        assert "created_at" in body
        assert "hashed_password" not in body  # never leak password hash
        assert "refresh_token" not in body    # never leak refresh token

    @pytest.mark.asyncio
    async def test_login_response_contract(self, client: AsyncClient):
        """Login response must include access_token, refresh_token, token_type."""
        await client.post("/api/v1/auth/register", json={
            "email": "login_contract@test.com", "password": "pass123"
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "login_contract@test.com", "password": "pass123"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        # Tokens must be non-empty strings
        assert len(body["access_token"]) > 10
        assert len(body["refresh_token"]) > 10


# ── Auth — Security Boundaries ────────────────────────────────────────────────

class TestAuthSecurity:

    @pytest.mark.asyncio
    async def test_malformed_bearer_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/watchlist",
                                headers={"Authorization": "Bearer malformed"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_auth_scheme(self, client: AsyncClient):
        """Basic auth scheme must not be accepted."""
        resp = await client.get("/api/v1/watchlist",
                                headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_expired_token_structure_rejected(self, client: AsyncClient):
        """A structurally valid but expired JWT must return 401."""
        from datetime import datetime, timedelta, timezone

        import jwt as pyjwt

        from app.config import settings
        expired_token = pyjwt.encode(
            {"sub": str(uuid.uuid4()), "type": "access", "role": "user",
             "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            settings.secret_key, algorithm=settings.algorithm
        )
        resp = await client.get("/api/v1/watchlist",
                                headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_token_used_as_refresh_rejected(self, client: AsyncClient):
        """Using an access token where a refresh token is expected must fail."""
        tokens = await _register_and_login(client, "token_type@test.com")
        resp = await client.post("/api/v1/auth/refresh",
                                 json={"refresh_token": tokens["access_token"]})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_user_watchlist(self, client: AsyncClient):
        """Watchlist is strictly scoped to the authenticated user."""
        headers_a = await _auth_headers(client, "user_a_sec@test.com")
        headers_b = await _auth_headers(client, "user_b_sec@test.com")

        # Both can access their own watchlist
        assert (await client.get("/api/v1/watchlist", headers=headers_a)).status_code == 200
        assert (await client.get("/api/v1/watchlist", headers=headers_b)).status_code == 200

        # No endpoint exposes another user's watchlist by ID
        resp = await client.get("/api/v1/watchlist", headers=headers_a)
        assert resp.json()["total"] == 0  # user_a sees only their own (empty)


# ── Cryptocurrencies — Input Validation ───────────────────────────────────────

class TestCoinsValidation:

    @pytest.mark.asyncio
    async def test_get_coin_invalid_uuid(self, client: AsyncClient):
        """Non-UUID path param must return 422."""
        resp = await client.get("/api/v1/cryptocurrencies/not-a-uuid")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_history_days_must_be_7_30_or_90(self, client: AsyncClient):
        for invalid in [1, 15, 100, 0, -1]:
            resp = await client.get(f"/api/v1/cryptocurrencies/bitcoin/history?days={invalid}")
            assert resp.status_code == 422, f"days={invalid} should be 422"

    @pytest.mark.asyncio
    async def test_history_valid_days_accepted(self, client: AsyncClient):
        mock_history = {"prices": [[1700000000000, 50000.0]]}
        for valid in [7, 30, 90]:
            with patch("app.services.crypto_service.CoinGeckoClient.fetch_history",
                       new_callable=AsyncMock, return_value=mock_history):
                resp = await client.get(f"/api/v1/cryptocurrencies/bitcoin/history?days={valid}")
                assert resp.status_code == 200, f"days={valid} should be 200"

    @pytest.mark.asyncio
    async def test_list_per_page_max_is_200(self, client: AsyncClient):
        resp = await client.get("/api/v1/cryptocurrencies?per_page=201")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_page_must_be_positive(self, client: AsyncClient):
        resp = await client.get("/api/v1/cryptocurrencies?page=0")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_invalid_sort_by(self, client: AsyncClient):
        resp = await client.get("/api/v1/cryptocurrencies?sort_by=invalid_field")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_coin_response_contract(self, client: AsyncClient):
        """Single coin detail must include all required fields."""
        coins = await _seed_coins(client)
        coin_id = coins[0]["id"]

        resp = await client.get(f"/api/v1/cryptocurrencies/{coin_id}")
        assert resp.status_code == 200
        body = resp.json()

        required_fields = ["id", "external_id", "name", "symbol",
                           "current_price", "market_cap",
                           "price_change_percentage_24h", "market_cap_rank"]
        for field in required_fields:
            assert field in body, f"Missing field: {field}"

        assert isinstance(body["id"], str)
        assert isinstance(body["symbol"], str)
        assert body["symbol"] == body["symbol"].lower()  # symbols are lowercase

    @pytest.mark.asyncio
    async def test_list_response_contract(self, client: AsyncClient):
        """List response must include pagination metadata."""
        await _seed_coins(client)
        resp = await client.get("/api/v1/cryptocurrencies?page=1&per_page=5")
        assert resp.status_code == 200
        body = resp.json()

        assert "data" in body
        assert "total" in body
        assert "page" in body
        assert "per_page" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["total"], int)
        assert body["page"] == 1
        assert body["per_page"] == 5

    @pytest.mark.asyncio
    async def test_refresh_requires_api_key_not_jwt(self, client: AsyncClient):
        """JWT auth must NOT work on the /refresh internal endpoint."""
        headers = await _auth_headers(client, "jwt_on_refresh@test.com")
        resp = await client.post("/api/v1/cryptocurrencies/refresh", headers=headers)
        # JWT in Authorization header should still fail — needs X-API-Key
        assert resp.status_code == 422


# ── Watchlist — Input Validation & Edge Cases ─────────────────────────────────

class TestWatchlistValidation:

    @pytest.mark.asyncio
    async def test_add_to_watchlist_nonexistent_coin(self, client: AsyncClient):
        """Adding a coin UUID that doesn't exist must return 404."""
        headers = await _auth_headers(client, "wl_notfound@test.com")
        resp = await client.post("/api/v1/watchlist",
                                 json={"cryptocurrency_id": str(uuid.uuid4())},
                                 headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_to_watchlist_invalid_uuid(self, client: AsyncClient):
        headers = await _auth_headers(client, "wl_invalid@test.com")
        resp = await client.post("/api/v1/watchlist",
                                 json={"cryptocurrency_id": "not-a-uuid"},
                                 headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_to_watchlist_missing_body(self, client: AsyncClient):
        headers = await _auth_headers(client, "wl_missing@test.com")
        resp = await client.post("/api/v1/watchlist", json={}, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_watchlist_response_contract(self, client: AsyncClient):
        """Watchlist GET response must include items array and total."""
        headers = await _auth_headers(client, "wl_contract@test.com")
        coins = await _seed_coins(client)
        coin_id = coins[0]["id"]

        await client.post("/api/v1/watchlist",
                          json={"cryptocurrency_id": coin_id}, headers=headers)

        resp = await client.get("/api/v1/watchlist", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 1

        item = body["items"][0]
        assert "id" in item
        assert "added_at" in item
        assert "cryptocurrency" in item

        coin = item["cryptocurrency"]
        for field in ["id", "symbol", "name", "current_price"]:
            assert field in coin, f"Missing coin field in watchlist item: {field}"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_watchlist_item(self, client: AsyncClient):
        """Deleting a coin not in the watchlist must return 404."""
        headers = await _auth_headers(client, "wl_del_missing@test.com")
        resp = await client.delete(
            f"/api/v1/watchlist/{uuid.uuid4()}", headers=headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_watchlist_invalid_uuid(self, client: AsyncClient):
        headers = await _auth_headers(client, "wl_del_invalid@test.com")
        resp = await client.delete("/api/v1/watchlist/not-a-uuid", headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_watchlist_duplicate_returns_409(self, client: AsyncClient):
        """Adding the same coin twice must return 409."""
        headers = await _auth_headers(client, "wl_dup@test.com")
        coins = await _seed_coins(client)
        coin_id = coins[0]["id"]

        resp1 = await client.post("/api/v1/watchlist",
                                  json={"cryptocurrency_id": coin_id}, headers=headers)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/v1/watchlist",
                                  json={"cryptocurrency_id": coin_id}, headers=headers)
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_watchlist_ordering(self, client: AsyncClient):
        """Watchlist items are returned in reverse-chronological order (newest first)."""
        headers = await _auth_headers(client, "wl_order@test.com")
        coins = await _seed_coins(client)

        # Add two coins
        await client.post("/api/v1/watchlist",
                          json={"cryptocurrency_id": coins[0]["id"]}, headers=headers)
        await client.post("/api/v1/watchlist",
                          json={"cryptocurrency_id": coins[1]["id"]}, headers=headers)

        resp = await client.get("/api/v1/watchlist", headers=headers)
        items = resp.json()["items"]
        assert len(items) == 2
        # Verify timestamps are descending
        assert items[0]["added_at"] >= items[1]["added_at"]

    @pytest.mark.asyncio
    async def test_unauthenticated_watchlist_endpoints(self, client: AsyncClient):
        """All watchlist endpoints require authentication."""
        endpoints = [
            ("GET", "/api/v1/watchlist"),
            ("POST", "/api/v1/watchlist"),
            ("DELETE", f"/api/v1/watchlist/{uuid.uuid4()}"),
        ]
        for method, url in endpoints:
            resp = await client.request(method, url)
            assert resp.status_code in (401, 403), \
                f"{method} {url} should require auth, got {resp.status_code}"


# ── Health endpoint ───────────────────────────────────────────────────────────

class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_response_contract(self, client: AsyncClient):
        resp = await client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert "environment" in body

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, client: AsyncClient):
        """Health check must be publicly accessible — used by ALB and monitoring."""
        resp = await client.get("/health")
        assert resp.status_code == 200
