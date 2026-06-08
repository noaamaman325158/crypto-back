import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_internal_api_key
from app.core.rate_limit import LIMITS, limiter
from app.db.database import get_db
from app.repositories.crypto_repo import CryptoRepository
from app.schemas.cryptocurrency import (
    CryptocurrencyResponse,
    HistoryResponse,
    PaginatedCoinsResponse,
    RefreshResponse,
)
from app.services.crypto_service import CryptoService

router = APIRouter(prefix="/cryptocurrencies", tags=["Cryptocurrencies"])


def get_crypto_service(db: AsyncSession = Depends(get_db)) -> CryptoService:
    return CryptoService(CryptoRepository(db))


@router.get("", response_model=PaginatedCoinsResponse)
@limiter.limit(LIMITS["coins_list"])
async def list_cryptocurrencies(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: Literal["market_cap_rank", "current_price", "market_cap", "name"] = "market_cap_rank",
    service: CryptoService = Depends(get_crypto_service),
):
    return await service.get_all(page=page, per_page=per_page, sort_by=sort_by)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    dependencies=[Depends(require_internal_api_key)],
)
@limiter.limit(LIMITS["coins_refresh"])
async def refresh_cryptocurrencies(
    request: Request,
    service: CryptoService = Depends(get_crypto_service),
):
    """Privileged endpoint — requires X-API-Key header (service-to-service auth)."""
    count = await service.refresh()
    return RefreshResponse(updated=count, message=f"Refreshed {count} cryptocurrencies from CoinGecko")


# IMPORTANT: /{external_id}/history MUST be registered before /{crypto_id}.
# FastAPI matches routes top-to-bottom. If /{crypto_id} (UUID) comes first,
# a request to /bitcoin/history would try to parse "bitcoin" as a UUID → 422.
# Specific sub-paths must always precede generic wildcard routes.
@router.get("/{external_id}/history", response_model=HistoryResponse)
@limiter.limit(LIMITS["coins_history"])
async def get_price_history(
    request: Request,
    external_id: str,
    days: Literal[7, 30, 90] = Query(30),
    service: CryptoService = Depends(get_crypto_service),
):
    return await service.get_history(external_id=external_id, days=days)


@router.get("/{crypto_id}", response_model=CryptocurrencyResponse)
@limiter.limit(LIMITS["coins_detail"])
async def get_cryptocurrency(
    request: Request,
    crypto_id: uuid.UUID,
    service: CryptoService = Depends(get_crypto_service),
):
    return await service.get_by_id(crypto_id)
