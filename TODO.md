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
  - **Circuit Breaker pattern** (using `pybreaker` or custom implementation):
    - States: CLOSED (normal) → OPEN (failing, reject fast) → HALF-OPEN (probe recovery)
    - Thresholds: open after 5 consecutive failures, probe after 60s
    - Prevents cascading failures — if CoinGecko is down, don't keep hammering it
    - Expose circuit state as a metric (`crypto_circuit_state{service="coingecko"}`)
    - Design:
      ```
      app/core/circuit_breaker.py   ← CircuitBreaker class with CLOSED/OPEN/HALF_OPEN states
      app/services/crypto_service.py ← wrap CoinGeckoClient calls with circuit breaker
      app/services/ai_insight_service.py ← wrap Claude API calls with circuit breaker
      ```
  - **Graceful Degradation** — what the API returns when the circuit is OPEN:
    - `GET /cryptocurrencies` — serve stale data from Redis cache (even if TTL expired)
      instead of returning 502. Add `X-Data-Freshness: stale` response header.
    - `GET /cryptocurrencies/:id/history` — return cached history if available,
      otherwise 503 with `Retry-After` header.
    - `GET /cryptocurrencies/:id/insight` — return cached insight if available,
      otherwise return a canned message: `{"insight": "AI analysis temporarily unavailable",
      "cached": false, "degraded": true}` instead of 502.
    - `POST /cryptocurrencies/refresh` — return 503 with circuit state in body
      instead of letting the request hang until timeout.
  - **Implementation steps**:
    - [ ] `app/core/circuit_breaker.py` — async-safe CircuitBreaker with configurable
          failure threshold, recovery timeout, and state change callbacks
    - [ ] Wire into `CoinGeckoClient` — all `fetch_*` methods go through the breaker
    - [ ] Wire into `AIInsightService` — Claude API call goes through a separate breaker
    - [ ] `app/services/crypto_service.py` — add stale-cache fallback when circuit is OPEN
    - [ ] `app/services/ai_insight_service.py` — add degraded response fallback
    - [ ] Expose circuit state at `GET /health/details` (not public `/health` — internal only)
    - [ ] Unit tests for all 3 states: CLOSED → OPEN → HALF_OPEN → CLOSED
    - [ ] Add circuit state to Prometheus metrics

## Backlog

- [ ] **k6 results in CI** — parse k6 JSON output and post p99 summary as a PR comment
- [ ] **Swagger enhancements** — add response examples to OpenAPI schema for better Postman UX
- [ ] **DB connection pool metrics** — expose asyncpg pool size / checked-out connections
- [ ] **Structured logging** — replace print/logging with structlog (JSON output for CloudWatch Logs Insights)
- [ ] **Health check depth** — extend `/health` to check DB + Redis connectivity (liveness vs readiness)
