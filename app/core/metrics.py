"""
Application-level Prometheus metrics.

Two categories:

1. AUTO — prometheus-fastapi-instrumentator instruments every HTTP endpoint
   automatically: request count, latency histogram, in-flight requests.
   Exposed at GET /metrics.

2. CUSTOM — business metrics that infra tools can't see:
   - Cache hit/miss (Redis)
   - Auth failures (security signal)
   - CoinGecko API calls vs cache hits
   - AI insight calls vs cache hits
   - DB connection pool saturation
   - Active gRPC connections

Grafana dashboards consume these alongside infrastructure metrics from
CloudWatch (ECS CPU/memory, RDS, ElastiCache, ALB).
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Cache metrics ─────────────────────────────────────────────────────────────

cache_hits = Counter(
    "crypto_cache_hits_total",
    "Number of Redis cache hits",
    ["cache_key_prefix"],  # e.g. "coins:list", "coins:detail", "insight"
)

cache_misses = Counter(
    "crypto_cache_misses_total",
    "Number of Redis cache misses",
    ["cache_key_prefix"],
)

# ── Auth metrics ──────────────────────────────────────────────────────────────

auth_attempts = Counter(
    "crypto_auth_attempts_total",
    "Number of authentication attempts",
    ["result"],  # "success" | "failure"
)

token_refresh_total = Counter(
    "crypto_token_refresh_total",
    "Number of token refresh operations",
    ["result"],  # "success" | "revoked" | "invalid"
)

# ── External API metrics ──────────────────────────────────────────────────────

coingecko_requests = Counter(
    "crypto_coingecko_requests_total",
    "Number of outbound CoinGecko API calls",
    ["operation"],  # "markets" | "detail" | "history"
)

coingecko_errors = Counter(
    "crypto_coingecko_errors_total",
    "Number of failed CoinGecko API calls",
    ["operation", "status_code"],
)

coingecko_latency = Histogram(
    "crypto_coingecko_request_duration_seconds",
    "CoinGecko API call latency",
    ["operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── AI insight metrics ────────────────────────────────────────────────────────

ai_insight_requests = Counter(
    "crypto_ai_insight_requests_total",
    "Total AI insight requests",
    ["source"],  # "cache" | "claude_api"
)

ai_insight_latency = Histogram(
    "crypto_ai_insight_duration_seconds",
    "Claude API call latency for insight generation",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ── Watchlist metrics ─────────────────────────────────────────────────────────

watchlist_operations = Counter(
    "crypto_watchlist_operations_total",
    "Watchlist CRUD operations",
    ["operation", "result"],  # operation: add|remove, result: success|conflict|not_found
)

# ── gRPC metrics ──────────────────────────────────────────────────────────────

grpc_requests = Counter(
    "crypto_grpc_requests_total",
    "Total gRPC requests",
    ["method", "status"],  # method: GetInsight, status: OK|NOT_FOUND|UNAVAILABLE
)

grpc_active_connections = Gauge(
    "crypto_grpc_active_connections",
    "Currently active gRPC connections",
)

# ── Coin refresh metrics ──────────────────────────────────────────────────────

coin_refresh_total = Counter(
    "crypto_coin_refresh_total",
    "Number of coin data refresh operations triggered",
)

coins_updated = Counter(
    "crypto_coins_updated_total",
    "Total coins upserted during refresh operations",
)
