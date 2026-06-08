import grpc

from app.grpc_generated.crypto.insight.v1 import insight_pb2, insight_pb2_grpc
from app.services.ai_insight_service import AIInsightService
from app.services.crypto_service import CoinGeckoClient


class InsightServicer(insight_pb2_grpc.InsightServiceServicer):
    """
    gRPC servicer for AI coin insights.

    Shares the exact same business logic as the REST endpoint — no duplication.
    The dual-protocol pattern (REST on :8000, gRPC on :50051) mirrors the
    Dataminr agentic-search architecture: one service, two transports.
    """

    async def GetInsight(
        self,
        request: insight_pb2.GetInsightRequest,
        context: grpc.aio.ServicerContext,
    ) -> insight_pb2.GetInsightResponse:
        coin_id = request.coin_id
        days = request.days or 30

        if not coin_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "coin_id is required")

        client = CoinGeckoClient()
        try:
            raw = await client.fetch_history(coin_id, days=days)
        except Exception as e:
            await context.abort(grpc.StatusCode.UNAVAILABLE, f"CoinGecko error: {e}")
        finally:
            await client.aclose()

        prices = [
            {"timestamp": str(ts), "price": price}
            for ts, price in raw.get("prices", [])
        ]

        if not prices:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"No price history available for '{coin_id}'",
            )

        service = AIInsightService()
        result = await service.get_insight(coin_id=coin_id, prices=prices)

        return insight_pb2.GetInsightResponse(
            coin_id=result.coin_id,
            insight=result.insight,
            generated_at=result.generated_at.isoformat(),
            cached=result.cached,
        )
