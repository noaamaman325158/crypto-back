import uuid

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token, verify_internal_api_key
from app.db.database import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    user = await UserRepository(db).get_by_id(uuid.UUID(user_id))
    if not user:
        raise UnauthorizedError("User not found")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise ForbiddenError("Admin access required")
    return current_user


async def require_internal_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
    """Service-to-service authentication via API key header."""
    verify_internal_api_key(x_api_key)
