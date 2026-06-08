"""Unit tests for AuthService — DB is fully mocked."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import ConflictError, UnauthorizedError
from app.models.user import User
from app.services.auth_service import AuthService

# Pre-computed bcrypt hash of "password123" — avoids calling bcrypt at import time
# and keeps unit tests fast (bcrypt is intentionally slow).
_HASHED_PASSWORD = "$2b$12$cD4ODbGwRjVXmgAuBJUMh.ghpOxJkabWqwdcDbRjpjR0lpTKF2FDK"


def _make_user(email: str = "test@example.com", role: str = "user") -> User:
    u = User()
    u.id = uuid.uuid4()
    u.email = email
    u.hashed_password = _HASHED_PASSWORD
    u.role = role
    u.refresh_token = None
    return u


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    return AuthService(mock_db)


@pytest.mark.asyncio
async def test_register_success(service):
    new_user = _make_user()
    with patch.object(service.repo, "get_by_email", return_value=None), \
         patch.object(service.repo, "create", return_value=new_user):
        result = await service.register("test@example.com", "password123")
    assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_raises(service):
    existing = _make_user()
    with patch.object(service.repo, "get_by_email", return_value=existing):
        with pytest.raises(ConflictError):
            await service.register("test@example.com", "password123")


@pytest.mark.asyncio
async def test_login_success(service):
    user = _make_user()
    with patch.object(service.repo, "get_by_email", return_value=user), \
         patch.object(service.repo, "update_refresh_token", new_callable=AsyncMock):
        tokens = await service.login("test@example.com", "password123")
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_raises(service):
    user = _make_user()
    with patch.object(service.repo, "get_by_email", return_value=user):
        with pytest.raises(UnauthorizedError):
            await service.login("test@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_login_unknown_email_raises(service):
    with patch.object(service.repo, "get_by_email", return_value=None):
        with pytest.raises(UnauthorizedError):
            await service.login("nobody@example.com", "password123")


@pytest.mark.asyncio
async def test_refresh_invalid_token_type_raises(service):
    from app.core.security import create_access_token
    access_token = create_access_token("user-1")  # type=access, not refresh
    with pytest.raises(UnauthorizedError):
        await service.refresh(access_token)


@pytest.mark.asyncio
async def test_refresh_revoked_token_raises(service):
    from app.core.security import create_refresh_token
    user = _make_user()
    refresh_token = create_refresh_token(str(user.id))
    user.refresh_token = "different-stored-token"  # DB has a different token — rotation occurred

    with patch.object(service.repo, "get_by_id", new=AsyncMock(return_value=user)):
        with pytest.raises(UnauthorizedError):
            await service.refresh(refresh_token)
