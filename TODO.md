# TODO — Crypto Dashboard Backend

## In Progress

- [ ] **Observability / Metrics**
  - `app/core/metrics.py` — Prometheus metric definitions created (cache, auth, CoinGecko, AI, gRPC, watchlist)
  - Still needed:
    - [ ] Wire metrics into services (increment counters on cache hit/miss, auth events, etc.)
    - [ ] Add `prometheus-fastapi-instrumentator` to `app/main.py` (auto HTTP metrics + `/metrics` endpoint)
    - [ ] Add Prometheus + Grafana to `docker-compose.yml` for local dev
    - [ ] Create `grafana/dashboards/` with a pre-built dashboard JSON (app + infra panels)
    - [ ] Add CloudWatch datasource config for infra metrics (ECS CPU/mem, RDS, ElastiCache, ALB)
    - [ ] Update Terraform to add CloudWatch metric alarms on SLO breaches
    - [ ] Update README with observability section

- [ ] **Repository Pattern — complete abstraction for DB portability**
  - Current state: repositories exist (`user_repo.py`, `crypto_repo.py`, `watchlist_repo.py`) and
    services use them correctly (no direct DB calls from endpoints). ✅
  - Missing for true DB-portability:
    - [ ] `app/repositories/base.py` — Abstract `BaseRepository[T]` interface with typed generics.
          Defines the contract: `get_by_id`, `create`, `update`, `delete`. Services depend on
          this interface, not the SQLAlchemy implementation.
    - [ ] Concrete repos implement `BaseRepository` — SQLAlchemy impl is one possible backend.
          A future `MongoRepository` or `DynamoRepository` would implement the same interface
          with zero changes to service code.
    - [ ] Move SQLAlchemy session (`AsyncSession`) dependency inside the concrete class, not the
          interface — so swapping the DB doesn't require changing service constructor signatures.
    - [ ] Unit tests mock `BaseRepository`, not the SQLAlchemy session — tests are then
          DB-agnostic by design.
  - Design:
    ```
    app/repositories/
    ├── base.py              ← Abstract BaseRepository[T] (Protocol or ABC)
    ├── user_repo.py         ← SQLAlchemyUserRepository(BaseRepository[User])
    ├── crypto_repo.py       ← SQLAlchemyCryptoRepository(BaseRepository[Cryptocurrency])
    └── watchlist_repo.py    ← SQLAlchemyWatchlistRepository(BaseRepository[WatchlistItem])
    ```

- [ ] **Circuit Breaker + Graceful Degradation**
  - **Where it applies** — two external dependencies that can fail independently:
    1. **CoinGecko API** — rate-limited, can go down, can be slow
    2. **Anthropic Claude API** — can be unavailable, expensive, has its own rate limits
  - **Circuit Breaker pattern** (using `pybreaker` or custom async implementation):
    - States: CLOSED (normal) → OPEN (failing, reject fast) → HALF-OPEN (probe recovery)
    - Thresholds: open after 5 consecutive failures, probe after 60s
    - Prevents cascading failures — if CoinGecko is down, don't keep hammering it
    - Expose circuit state as a metric (`crypto_circuit_state{service="coingecko"}`)
    - Design:
      ```
      app/core/circuit_breaker.py   ← async CircuitBreaker with CLOSED/OPEN/HALF_OPEN states
      app/services/crypto_service.py ← wrap CoinGeckoClient calls with breaker
      app/services/ai_insight_service.py ← wrap Claude API calls with separate breaker
      ```
  - **Graceful Degradation** — what the API returns when the circuit is OPEN:
    - `GET /cryptocurrencies` → serve stale Redis cache + `X-Data-Freshness: stale` header
    - `GET /cryptocurrencies/:id/history` → cached history or 503 + `Retry-After`
    - `GET /cryptocurrencies/:id/insight` → cached insight or `{"degraded": true, "insight": "temporarily unavailable"}`
    - `POST /cryptocurrencies/refresh` → 503 with circuit state in body
  - **Implementation steps**:
    - [ ] `app/core/circuit_breaker.py` — async-safe CircuitBreaker with state change callbacks
    - [ ] Wire into `CoinGeckoClient` + `AIInsightService`
    - [ ] Stale-cache fallback in `crypto_service.py` and `ai_insight_service.py`
    - [ ] Expose circuit state at `GET /health/details` (internal only)
    - [ ] Unit tests for all 3 state transitions: CLOSED → OPEN → HALF_OPEN → CLOSED
    - [ ] Circuit state exposed as Prometheus gauge

- [ ] **Caching Strategy — formalise and extend**
  - Current state: Redis cache-aside is used for coin list/detail (60s TTL) and AI insights (1h TTL). ✅
  - Missing for a robust caching strategy:
    - [ ] **Cache warming** — on `/refresh` trigger, pre-populate cache for top-N coins
          so the first request after a refresh is never a cache miss
    - [ ] **Cache stampede protection** — when a popular cache key expires, many concurrent
          requests all miss and hit DB/CoinGecko simultaneously. Fix: probabilistic early
          expiration (XFetch algorithm) or a per-key mutex (Redis `SET NX` lock)
    - [ ] **TTL tiering** — different TTLs based on data volatility:
          - Coin list: 60s (changes every minute)
          - Coin detail: 60s
          - Price history: 5 min (historical data doesn't change)
          - AI insight: 1h (already correct ✅)
          - Auth token blacklist: match token expiry
    - [ ] **Cache eviction on write** — currently `/refresh` deletes `coins:list:*` keys ✅
          but doesn't invalidate individual coin detail keys. Add targeted invalidation.
    - [ ] **Cache miss rate alerting** — if cache miss rate > 50% for >5 min, alert
          (means Redis is down or keys are evicting too fast)
    - [ ] `app/core/cache.py` — add `cache_get_or_set()` helper that wraps the
          cache-aside pattern in one call with stampede protection
    - [ ] Document TTL strategy and rationale in code comments + README

- [ ] **Global Exception Handler (Middleware)**
  - Current state: `HTTPException` subclasses exist (`NotFoundError`, `ConflictError`, etc.)
    but unhandled exceptions return FastAPI's default 500 with full stack trace. ✅ partial
  - Missing:
    - [ ] `app/core/exception_handler.py` — global exception handler middleware:
          ```python
          @app.exception_handler(Exception)
          async def unhandled_exception_handler(request, exc):
              # Log with structured logger (correlation ID, path, method)
              # Return consistent error shape: {"error": "...", "request_id": "..."}
              # Never leak stack traces to clients
              # Increment error counter metric
          ```
    - [ ] **Consistent error response shape** — all errors (4xx and 5xx) return:
          ```json
          {
            "error": "human-readable message",
            "code": "MACHINE_READABLE_CODE",
            "request_id": "uuid-for-tracing",
            "timestamp": "2026-06-09T..."
          }
          ```
          Currently 422 validation errors return FastAPI's default shape (different from our 404/409 shape)
    - [ ] **Request ID middleware** — inject `X-Request-ID` header on every response
          (generate if not provided by caller, pass through if provided). Enables distributed tracing.
    - [ ] **Error classification** — distinguish operational errors (4xx — client's fault,
          don't alert) from programmer errors (5xx — our fault, alert immediately)
    - [ ] Wire to structured logger so every unhandled error logs: request_id, path,
          method, user_id (if authenticated), error type, stack trace
    - [ ] Add to unit tests: verify 500 errors never leak stack traces

- [ ] **Structured Logging**
  - Current state: standard Python `logging` module, unstructured text output. ❌
  - Why it matters: CloudWatch Logs Insights can only query structured (JSON) logs.
    Unstructured logs are grep-only — useless for production debugging at scale.
  - **Stack**: `structlog` (best async support, works with standard logging)
  - **What every log line must include**:
    ```json
    {
      "timestamp": "2026-06-09T10:23:45.123Z",
      "level": "info",
      "logger": "app.services.crypto_service",
      "request_id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "uuid-or-null",
      "method": "GET",
      "path": "/api/v1/cryptocurrencies",
      "duration_ms": 23,
      "message": "coin list served from cache",
      "cache_hit": true,
      "environment": "production"
    }
    ```
  - **Implementation steps**:
    - [ ] `pip install structlog==25.x` — add to requirements.txt
    - [ ] `app/core/logging.py` — configure structlog: JSON renderer in prod,
          console renderer in dev, bind `request_id` and `user_id` to context
    - [ ] `app/middleware/logging_middleware.py` — request/response logging middleware:
          log every request with method, path, status, duration_ms, request_id
    - [ ] Replace all `logger = logging.getLogger(__name__)` with structlog loggers
    - [ ] Bind `request_id` at request start, available everywhere in the call stack
          via `structlog.contextvars.bind_contextvars(request_id=...)`
    - [ ] CloudWatch Logs Insights query examples in README:
          ```
          fields @timestamp, request_id, path, duration_ms
          | filter level = "error"
          | sort @timestamp desc
          | limit 20
          ```
    - [ ] Add log sampling for high-volume endpoints (log 1% of successful coin list requests,
          100% of errors) to control CloudWatch costs

## Backlog

- [ ] **k6 results in CI** — parse k6 JSON output and post p99 summary as a PR comment
- [ ] **Swagger enhancements** — add response examples to OpenAPI schema for better Postman UX
- [ ] **DB connection pool metrics** — expose asyncpg pool size / checked-out connections
- [ ] **Health check depth** — extend `/health` to check DB + Redis connectivity (liveness vs readiness)
