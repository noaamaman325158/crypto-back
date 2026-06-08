from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import LIMITS, limiter
from app.db.database import get_db
from app.schemas.user import (
    RefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit(LIMITS["auth_register"])
async def register(
    request: Request,
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.register(email=body.email, password=body.password)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LIMITS["auth_login"])
async def login(
    request: Request,
    body: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.login(email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(LIMITS["auth_refresh"])
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.refresh(body.refresh_token)
