"""
Redis-backed rate limiter and centralised limit definitions.

The limiter lives here (not in main.py) to avoid circular imports:
  main.py → router → endpoints → limiter

Using Redis as storage_uri means limits are enforced across all container
instances — a client cannot bypass limits by hitting a different ECS task.

Limit tiers (by endpoint sensitivity):
  - Auth (login/register): tight — brute-force / credential stuffing protection.
    10 req/min is comfortable for humans, painful for automated attacks.
  - Read (coins, watchlist): relaxed — responses are Redis-cached, DB load is low.
  - AI insight: tight — each cache miss invokes the Claude API (cost + latency).
  - Internal refresh: tightest — triggers a CoinGecko API call on every hit.

When a limit is exceeded, slowapi returns HTTP 429 Too Many Requests with
a Retry-After header indicating when the client may try again.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    # Default applied to any endpoint that doesn't declare its own limit.
    default_limits=["200/minute"],
)

# Production SLOs — enforced when ENVIRONMENT=production.
# In development/test the multiplier is 100x so performance tests are not
# throttled by rate limits (which are a security control, not a perf target).
_PROD = settings.environment == "production"

def _limit(prod_limit: str) -> str:
    """Return prod_limit in production, 100x the count otherwise."""
    if _PROD:
        return prod_limit
    count, period = prod_limit.split("/")
    return f"{int(count) * 100}/{period}"

# Limit strings: "<count>/<period>" — period: second | minute | hour | day
LIMITS = {
    # Auth — brute-force protection
    "auth_register": _limit("10/minute"),
    "auth_login":    _limit("10/minute"),
    "auth_refresh":  _limit("20/minute"),

    # Read — cheap (cached), allow reasonable traffic
    "coins_list":    _limit("60/minute"),
    "coins_detail":  _limit("60/minute"),
    "coins_history": _limit("30/minute"),

    # AI insight — Claude API call (cached 1h but first call is expensive)
    "coins_insight": _limit("10/minute"),

    # Watchlist — authenticated, low volume expected
    "watchlist_read":  _limit("60/minute"),
    "watchlist_write": _limit("20/minute"),

    # Internal refresh — triggers CoinGecko API call
    "coins_refresh": _limit("5/minute"),
}
