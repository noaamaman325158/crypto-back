from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.core.rate_limit import LIMITS, limiter
from app.models.user import User
from app.providers.coingecko import get_crypto_provider
from app.schemas.cryptocurrency import InsightResponse
from app.services.ai_insight_service import AIInsightService

router = APIRouter(prefix="/cryptocurrencies", tags=["AI Insights"])


@router.get("/{external_id}/insight", response_model=InsightResponse)
@limiter.limit(LIMITS["coins_insight"])
async def get_coin_insight(
    request: Request,
    external_id: str,
    _: User = Depends(get_current_user),
):
    """
    Returns a Claude-generated 2-3 sentence trend analysis based on 30 days of price data.
    Results are cached for 1 hour to minimize API cost.
    Rate limited to 10/minute — each uncached call invokes the Claude API.
    """
    provider = get_crypto_provider()
    try:
        raw = await provider.fetch_history(external_id, days=30)
        prices = [
            {"timestamp": str(ts), "price": price}
            for ts, price in raw.get("prices", [])
        ]
    finally:
        await provider.aclose()

    if not prices:
        raise NotFoundError(f"No price history available for '{external_id}'")

    service = AIInsightService()
    return await service.get_insight(coin_id=external_id, prices=prices)
