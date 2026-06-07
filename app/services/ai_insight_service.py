from datetime import datetime, timezone

import anthropic

from app.config import settings
from app.core.cache import cache_get, cache_set
from app.schemas.cryptocurrency import InsightResponse


class AIInsightService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def get_insight(self, coin_id: str, prices: list[dict]) -> InsightResponse:
        cache_key = f"insight:{coin_id}"
        cached = await cache_get(cache_key)
        if cached:
            return InsightResponse(**cached, cached=True)

        insight_text = self._generate_insight(coin_id, prices)
        result = InsightResponse(
            coin_id=coin_id,
            insight=insight_text,
            generated_at=datetime.now(timezone.utc),
        )
        await cache_set(cache_key, result.model_dump(mode="json"), ttl=3600)
        return result

    def _generate_insight(self, coin_id: str, prices: list[dict]) -> str:
        # Use last 30 data points to stay within a concise prompt
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
