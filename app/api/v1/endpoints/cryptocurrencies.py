import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_internal_api_key
from app.core.idempotency import check_idempotency, idempotency_key_header, store_idempotency
from app.core.logging import get_logger
from app.core.rate_limit import LIMITS, limiter
from app.db.database import get_db
from app.providers.coingecko import get_crypto_provider
from app.repositories.crypto_repo import CryptoRepository
from app.schemas.cryptocurrency import (
    CryptocurrencyResponse,
    HistoryResponse,
    PaginatedCoinsResponse,
    RefreshResponse,
    TopMoversResponse,
)
from app.services.crypto_service import CryptoService

router = APIRouter(prefix="/cryptocurrencies", tags=["Cryptocurrencies"])
logger = get_logger(__name__)


def get_crypto_service(db: AsyncSession = Depends(get_db)) -> CryptoService:
    return CryptoService(CryptoRepository(db), get_crypto_provider())


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


@router.get(
    "/top-movers",
    response_model=TopMoversResponse,
    summary="Top gainers and losers by 24h price change",
)
@limiter.limit(LIMITS["coins_list"])
async def get_top_movers(
    request: Request,
    limit: int = Query(5, ge=1, le=20, description="Number of coins in each list"),
    service: CryptoService = Depends(get_crypto_service),
):
    """Returns the top gaining and losing coins over the last 24 hours.

    Useful for surfacing market momentum without paginating through all coins.
    Results are cached for 60 seconds alongside the main coin list.
    """
    return await service.get_top_movers(limit=limit)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=202,
    dependencies=[Depends(require_internal_api_key)],
)
@limiter.limit(LIMITS["coins_refresh"])
async def refresh_cryptocurrencies(
    request: Request,
    service: CryptoService = Depends(get_crypto_service),
    idempotency_key: str | None = Depends(idempotency_key_header),
):
    """Privileged endpoint — requires X-API-Key header (service-to-service auth).

    Returns 202 immediately. The CoinGecko fetch and DB upsert run in the
    background so the caller is not blocked for 5–15 seconds.

    Supports idempotency: send `Idempotency-Key: <uuid>` to safely retry
    without triggering duplicate CoinGecko refreshes within 30 seconds.
    """
    cached = await check_idempotency(idempotency_key)
    if cached:
        return Response(status_code=202)

    async def _run(svc: CryptoService) -> None:
        try:
            await svc.refresh()
        except Exception as e:
            logger.error("async_refresh_failed", error=str(e))

    asyncio.create_task(_run(service))
    await store_idempotency(idempotency_key, {"scheduled": True}, ttl=30)
    return Response(status_code=202)


# IMPORTANT: /{external_id}/history and /top-movers MUST be registered before /{crypto_id}.
# FastAPI matches routes top-to-bottom — a UUID path param would try to parse
# "top-movers" or "bitcoin" as a UUID and return 422.
@router.get("/{external_id}/history", response_model=HistoryResponse)
@limiter.limit(LIMITS["coins_history"])
async def get_price_history(
    request: Request,
    external_id: str,
    days: int = Query(30, ge=7, description="Must be 7, 30, or 90"),
    service: CryptoService = Depends(get_crypto_service),
):
    if days not in (7, 30, 90):
        raise HTTPException(status_code=422, detail="days must be 7, 30, or 90")
    return await service.get_history(external_id=external_id, days=days)


@router.get("/{crypto_id}", response_model=CryptocurrencyResponse)
@limiter.limit(LIMITS["coins_detail"])
async def get_cryptocurrency(
    request: Request,
    crypto_id: uuid.UUID,
    service: CryptoService = Depends(get_crypto_service),
):
    return await service.get_by_id(crypto_id)
