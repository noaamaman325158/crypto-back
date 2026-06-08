import asyncio
from datetime import datetime, timezone
from functools import partial

import anthropic

from app.config import settings
from app.core.cache import cache_get, cache_set
from app.core.exceptions import ExternalServiceError
from app.schemas.cryptocurrency import InsightResponse


class AIInsightService:
    def __init__(self):
        # Anthropic SDK is sync — we run it in a thread pool to avoid blocking
        # the asyncio event loop. A blocked event loop would freeze ALL requests.
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def get_insight(self, coin_id: str, prices: list[dict]) -> InsightResponse:
        cache_key = f"insight:{coin_id}"
        cached = await cache_get(cache_key)
        if cached:
            return InsightResponse(**cached, cached=True)

        insight_text = await self._generate_insight_async(coin_id, prices)
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
            raise ExternalServiceError(f"Anthropic authentication failed: {e}") from e
        except anthropic.RateLimitError as e:
            raise ExternalServiceError("Anthropic rate limit exceeded — try again later") from e
        except anthropic.APIConnectionError as e:
            raise ExternalServiceError(f"Anthropic unreachable: {e}") from e
        except anthropic.APIError as e:
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
