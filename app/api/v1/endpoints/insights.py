from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.core.rate_limit import LIMITS, limiter
from app.db.database import get_db
from app.models.user import User
from app.repositories.price_history_repo import PriceHistoryRepository
from app.schemas.cryptocurrency import InsightResponse
from app.services.ai_insight_service import AIInsightService

router = APIRouter(prefix="/cryptocurrencies", tags=["AI Insights"])


@router.get("/{external_id}/insight", response_model=InsightResponse)
@limiter.limit(LIMITS["coins_insight"])
async def get_coin_insight(
    request: Request,
    external_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a Claude-generated 2-3 sentence trend analysis based on 30 days of price data.

    Price history is read from PostgreSQL (populated by the background worker) —
    no CoinGecko call at request time, consistent with the push-based pipeline.
    Results are cached for 1 hour to minimize API cost.
    Rate limited to 10/minute — each uncached call invokes the Claude API.
    """
    rows = await PriceHistoryRepository(db).get_history(external_id, days=30)
    if not rows:
        raise NotFoundError(
            f"No price history available for '{external_id}'. "
            "Data may not have been collected yet — check back after the next refresh cycle."
        )
    prices = [
        {"timestamp": r.recorded_at.isoformat(), "price": r.price}
        for r in rows
    ]

    service = AIInsightService()
    return await service.get_insight(coin_id=external_id, prices=prices)
