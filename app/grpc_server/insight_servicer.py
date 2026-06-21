import grpc

from app.db.database import AsyncSessionLocal
from app.grpc_generated.crypto.insight.v1 import insight_pb2, insight_pb2_grpc
from app.repositories.price_history_repo import PriceHistoryRepository
from app.services.ai_insight_service import AIInsightService


class InsightServicer(insight_pb2_grpc.InsightServiceServicer):
    """
    gRPC servicer for AI coin insights.

    Shares the exact same business logic as the REST endpoint — no duplication.
    The dual-protocol pattern (REST on :8000, gRPC on :50051) mirrors the
    Dataminr agentic-search architecture: one service, two transports.
    """

    async def GetInsight(  # type: ignore[override]
        self,
        request: insight_pb2.GetInsightRequest,  # type: ignore[name-defined]
        context: grpc.aio.ServicerContext,
    ) -> insight_pb2.GetInsightResponse:  # type: ignore[name-defined]
        coin_id = request.coin_id
        days = request.days or 30

        if not coin_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "coin_id is required")

        # Read price history from PostgreSQL (populated by the background worker),
        # mirroring the REST endpoint — no CoinGecko call at request time.
        async with AsyncSessionLocal() as db:
            rows = await PriceHistoryRepository(db).get_history(coin_id, days=days)

        prices = [
            {"timestamp": r.recorded_at.isoformat(), "price": r.price}
            for r in rows
        ]

        if not prices:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"No price history available for '{coin_id}'",
            )

        service = AIInsightService()
        result = await service.get_insight(coin_id=coin_id, prices=prices)

        return insight_pb2.GetInsightResponse(  # type: ignore[attr-defined]
            coin_id=result.coin_id,
            insight=result.insight,
            generated_at=result.generated_at.isoformat(),
            cached=result.cached,
        )
