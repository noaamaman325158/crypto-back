import asyncio
import time
from datetime import datetime, timezone
from functools import partial

import anthropic

from app.config import settings
from app.core.cache import cache_get, cache_set
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.core.metrics import ai_insight_latency, ai_insight_requests, cache_hits, cache_misses
from app.schemas.cryptocurrency import InsightResponse

logger = get_logger(__name__)


class AIInsightService:
    def __init__(self):
        # Anthropic SDK is sync — we run it in a thread pool to avoid blocking
        # the asyncio event loop. A blocked event loop would freeze ALL requests.
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def get_insight(self, coin_id: str, prices: list[dict]) -> InsightResponse:
        cache_key = f"insight:{coin_id}"
        cached = await cache_get(cache_key)
        if cached:
            cache_hits.labels(cache_key_prefix="insight").inc()
            ai_insight_requests.labels(source="cache").inc()
            logger.info("ai_insight_cache_hit", coin_id=coin_id)
            return InsightResponse(**cached, cached=True)
        cache_misses.labels(cache_key_prefix="insight").inc()

        ai_insight_requests.labels(source="claude_api").inc()
        logger.info("ai_insight_claude_request", coin_id=coin_id, price_points=len(prices))
        t0 = time.perf_counter()
        insight_text = await self._generate_insight_async(coin_id, prices)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        ai_insight_latency.observe(time.perf_counter() - t0)
        logger.info("ai_insight_generated", coin_id=coin_id, duration_ms=duration_ms)

        result = InsightResponse(
            coin_id=coin_id,
            insight=insight_text,
            generated_at=datetime.now(timezone.utc),
        )
        await cache_set(cache_key, result.model_dump(mode="json"), ttl=3600)
        return result

    async def _generate_insight_async(self, coin_id: str, prices: list[dict]) -> str:
        """
        Run the sync Anthropic SDK call in a thread pool executor so it doesn't
        block the asyncio event loop. Any Anthropic error is mapped to 502.
        """
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                partial(self._generate_insight, coin_id, prices),
            )
        except anthropic.AuthenticationError as e:
            logger.error("ai_insight_auth_error", coin_id=coin_id, error=str(e))
            raise ExternalServiceError(f"Anthropic authentication failed: {e}") from e
        except anthropic.RateLimitError as e:
            logger.warning("ai_insight_rate_limited", coin_id=coin_id)
            raise ExternalServiceError("Anthropic rate limit exceeded — try again later") from e
        except anthropic.APIConnectionError as e:
            logger.error("ai_insight_connection_error", coin_id=coin_id, error=str(e))
            raise ExternalServiceError(f"Anthropic unreachable: {e}") from e
        except anthropic.APIError as e:
            logger.error("ai_insight_api_error", coin_id=coin_id, error=str(e))
            raise ExternalServiceError(f"Anthropic API error: {e}") from e

    def _generate_insight(self, coin_id: str, prices: list[dict]) -> str:
        sample = prices[-30:]
        price_lines = "\n".join(
            f"{p['timestamp']}: ${p['price']:,.4f}" for p in sample
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Analyze this {coin_id.upper()} price data and provide a 2-3 sentence "
                        "insight on recent price trend, momentum, and any notable price levels. "
                        "Be concise, factual, and analytical. Do not give financial advice.\n\n"
                        f"{price_lines}"
                    ),
                }
            ],
        )
        return message.content[0].text
