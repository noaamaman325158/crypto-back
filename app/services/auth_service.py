from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.metrics import auth_attempts, token_refresh_total
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import TokenResponse


class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def register(self, email: str, password: str) -> User:
        if await self.repo.get_by_email(email):
            raise ConflictError("Email already registered")
        return await self.repo.create(email=email, hashed_password=hash_password(password))

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            auth_attempts.labels(result="failure").inc()
            raise UnauthorizedError("Invalid email or password")

        auth_attempts.labels(result="success").inc()
        access_token = create_access_token(str(user.id), role=user.role)
        refresh_token = create_refresh_token(str(user.id))
        await self.repo.update_refresh_token(user.id, refresh_token)

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            token_refresh_total.labels(result="invalid").inc()
            raise UnauthorizedError("Invalid token type")

        import uuid
        user = await self.repo.get_by_id(uuid.UUID(payload["sub"]))
        if not user or user.refresh_token != refresh_token:
            token_refresh_total.labels(result="revoked").inc()
            raise UnauthorizedError("Refresh token revoked or invalid")

        access_token = create_access_token(str(user.id), role=user.role)
        new_refresh = create_refresh_token(str(user.id))
        await self.repo.update_refresh_token(user.id, new_refresh)
        token_refresh_total.labels(result="success").inc()

        return TokenResponse(access_token=access_token, refresh_token=new_refresh)
