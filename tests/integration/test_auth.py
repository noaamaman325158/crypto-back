import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "user"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "pass"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "login@example.com", "password": "mypassword"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@example.com", "password": "mypassword"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "badpass@example.com", "password": "correct"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "badpass@example.com", "password": "wrong"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/watchlist")
    # HTTPBearer returns 403 when Authorization header is missing entirely
    # (starlette behaviour varies by version — accept either 401 or 403)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """Access token can be rotated using the refresh token."""
    await client.post("/api/v1/auth/register", json={
        "email": "refresh@example.com", "password": "password123"
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "refresh@example.com", "password": "password123"
    })
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 10
    assert len(data["refresh_token"]) > 10
    # Note: token revocation (old token → 401) is tested at unit level in
    # tests/unit/test_auth_service.py::test_refresh_revoked_token_raises.
    # The integration test session rolls back per-request, so the DB write
    # from rotation isn't visible across requests in this fixture.


@pytest.mark.asyncio
async def test_invalid_token_rejected(client: AsyncClient):
    """A tampered or expired token must be rejected with 401."""
    resp = await client.get(
        "/api/v1/watchlist",
        headers={"Authorization": "Bearer not.a.valid.token"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client: AsyncClient):
    """A garbage refresh token must be rejected."""
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
    assert resp.status_code == 401
