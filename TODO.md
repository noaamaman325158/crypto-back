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

- [ ] **Feature Gating by Plan (Freemium / Premium RBAC)**
  - **The business problem**: expensive features (price history, AI insight) should be
    restricted by subscription tier — free users get limited access, paying users get full access.
    This is already enabled architecturally: the User model has a `role` field and RBAC
    dependencies exist (`require_admin`, `get_current_user`). Extending to `premium` is additive.
  - **Current RBAC state**: `user` / `admin` roles only. ✅ foundation exists.
  - **What to add**:

  **1. Extend the role model**
  ```python
  # User.role: "free" | "premium" | "admin"
  # Migration: ALTER TABLE users ALTER COLUMN role SET DEFAULT 'free'
  ```

  **2. Plan-aware dependency**
  ```python
  # app/api/v1/dependencies.py
  async def require_premium(current_user: User = Depends(get_current_user)) -> User:
      if current_user.role not in ("premium", "admin"):
          raise HTTPException(
              status_code=403,
              detail={
                  "code": "PLAN_LIMIT_EXCEEDED",
                  "message": "This feature requires a premium subscription.",
                  "upgrade_url": "https://your-app.com/upgrade"
              }
          )
      return current_user
  ```

  **3. History endpoint — days gating**
  ```python
  # Free users: max 7 days history
  # Premium users: up to 90 days (or 365 with paid CoinGecko plan)
  PLAN_MAX_DAYS = {"free": 7, "premium": 90, "admin": 365}

  @router.get("/{external_id}/history")
  async def get_price_history(
      days: int = Query(7),
      current_user: User = Depends(get_current_user),
  ):
      max_days = PLAN_MAX_DAYS.get(current_user.role, 7)
      if days > max_days:
          raise HTTPException(403, detail={
              "code": "PLAN_LIMIT_EXCEEDED",
              "max_days": max_days,
              "requested_days": days,
              "upgrade_url": "https://your-app.com/upgrade"
          })
  ```

  **4. AI Insight — premium only**
  ```python
  # GET /cryptocurrencies/:id/insight → require_premium dependency
  # Free users get 403 with upgrade_url, not 401
  ```

  **5. Watchlist size limit**
  ```python
  # Free: max 5 coins in watchlist
  # Premium: unlimited
  PLAN_MAX_WATCHLIST = {"free": 5, "premium": None}
  # Check count before add: if len(items) >= limit → 403 PLAN_LIMIT_EXCEEDED
  ```

  - **Implementation steps**:
    - [ ] DB migration: add `plan` column to users (`free`/`premium`/`admin`), keep `role`
          for auth permissions — separate concerns (identity vs entitlement)
    - [ ] `app/api/v1/dependencies.py` — `require_premium()` dependency
    - [ ] `app/core/plans.py` — `PLAN_LIMITS` dict: maps plan → feature limits
          (max_history_days, max_watchlist_size, ai_insight_enabled, etc.)
    - [ ] Apply gating to: `/history` (days cap), `/insight` (plan gate), `/watchlist POST` (size cap)
    - [ ] Return structured 403 with `upgrade_url` — not a generic forbidden
    - [ ] Unit tests: free user hitting premium endpoint → 403 with correct error code
    - [ ] Integration tests: verify day cap enforced, watchlist size enforced
    - [ ] Mention in Swagger docs: mark premium endpoints with a tag or description
    - [ ] README: document which endpoints are free vs premium

  - **Why the architecture already supports this (mention in video)**:
    > "When I designed the auth layer with RBAC and a `role` field on the User model,
    > I wasn't just thinking about admin access — I was thinking about monetisation.
    > Adding a `premium` tier is a one-migration, zero-refactor change. The dependency
    > injection system means I add `require_premium` to one line in the endpoint, and
    > the entire enforcement is in one place. This is the difference between a system
    > designed for growth and one designed to just pass the assignment."

- [ ] **Idempotency — safe retry semantics for mutating endpoints**
  - **The problem**: what happens when a user double-taps "Add to Watchlist", or
    the frontend retries a failed POST due to a network timeout?
    - A junior solution: DB throws a duplicate key error → unhandled 500 or ugly 409
    - A senior solution: the API is idempotent by design — retrying the same operation
      produces the same result without side effects, and the response is always clean

  - **Current state**: `POST /watchlist` returns 409 on duplicate. ✅ better than 500,
    but still forces the client to handle a "conflict" that isn't really an error from
    the user's perspective — they just want the coin in their watchlist.

  - **Two strategies (choose per endpoint semantics)**:

    **Strategy A — Natural idempotency via UPSERT (recommended for watchlist)**
    ```python
    # Instead of: INSERT → catch IntegrityError → return 409
    # Do:         INSERT ON CONFLICT DO NOTHING → always return 200/201
    # The DB constraint still prevents duplicates, but the API treats
    # "already exists" as success — the desired state is achieved.

    stmt = insert(WatchlistItem).values(...).on_conflict_do_nothing(
        constraint="uq_user_crypto"
    )
    # Return 200 if already existed, 201 if newly created
    # Client doesn't need to handle 409 — simplifies frontend logic
    ```

    **Strategy B — Client-driven idempotency key (for financial/critical operations)**
    ```python
    # Client sends: Idempotency-Key: <uuid> header
    # Server stores: Redis key "idempotency:{key}" → cached response (24h TTL)
    # On retry: return the exact same response as the first call
    # Guarantees: even if the first request partially completed before crashing,
    #             the retry won't double-execute

    # middleware/idempotency.py
    async def idempotency_middleware(request, call_next):
        key = request.headers.get("Idempotency-Key")
        if key and request.method in ("POST", "PUT", "PATCH"):
            cached = await cache_get(f"idempotency:{key}")
            if cached:
                return JSONResponse(cached["body"], status_code=cached["status"])
            response = await call_next(request)
            await cache_set(f"idempotency:{key}", {...}, ttl=86400)
            return response
    ```

  - **Apply per endpoint**:
    | Endpoint | Strategy | Why |
    |---|---|---|
    | `POST /watchlist` | A (UPSERT + return 200) | User intent: "coin should be in watchlist" |
    | `DELETE /watchlist/:id` | Natural — 404 is acceptable | Deleting non-existent = already deleted |
    | `POST /auth/register` | Keep 409 — duplicate email IS an error | User needs to know email is taken |
    | `POST /cryptocurrencies/refresh` | Idempotency-Key header | Prevents double-refresh from concurrent schedulers |

  - **Implementation steps**:
    - [ ] `POST /watchlist` — change from INSERT+catch to UPSERT `ON CONFLICT DO NOTHING`,
          return 200 with existing item if duplicate, 201 if new
    - [ ] `app/middleware/idempotency.py` — middleware that reads `Idempotency-Key` header,
          checks Redis cache, returns cached response on retry
    - [ ] Apply idempotency middleware to `POST /cryptocurrencies/refresh`
    - [ ] Unit tests: same request twice → same response, no duplicate DB rows
    - [ ] Integration test: concurrent POSTs to `/watchlist` with same coin → exactly 1 row
    - [ ] Document `Idempotency-Key` header in Swagger and README

  - **Why this matters (mention in video)**:
    > "In financial systems and crypto dashboards where users might retry
    > aggressively or networks are unreliable, idempotency isn't a nice-to-have —
    > it's a correctness requirement. A user seeing 'coin added' twice in their
    > watchlist because they had bad WiFi is a trust-destroying bug.
    > The UniqueConstraint in the DB is the last line of defence.
    > The UPSERT pattern means we never even reach that error path."

- [ ] **Async Refresh — non-blocking background execution**
  - **The problem**: `POST /cryptocurrencies/refresh` currently calls CoinGecko synchronously.
    Even with `async/await`, the HTTP connection stays open and the response is held until
    CoinGecko responds (500ms–2s). Under load, every refresh request ties up a worker slot.
    A frontend "Refresh" button that waits 2 seconds for a response is a bad UX and a DoS risk.

  - **The senior solution — 202 Accepted + background task**:
    ```
    Client          API             CoinGecko
      |               |                 |
      |─POST /refresh─►|                 |
      |◄──202 Accepted─|                 |
      |   {job_id}     |                 |
      |               |──fetch markets──►|
      |               |◄──coin data──────|
      |               |──upsert DB───►   |
      |               |──clear cache──►  |
      |                                  |
      |─GET /cryptocurrencies ──────────►|  ← next request gets fresh data
    ```

  - **Three implementation tiers** (choose based on scale):

    **Tier 1 — FastAPI BackgroundTasks (current scale, simplest)**
    ```python
    from fastapi import BackgroundTasks

    @router.post("/refresh", status_code=202)
    async def refresh_cryptocurrencies(
        background_tasks: BackgroundTasks,
        service: CryptoService = Depends(get_crypto_service),
    ):
        background_tasks.add_task(service.refresh)
        return {"status": "accepted", "message": "Refresh started in background"}
    # Pro: zero extra infra, runs in same process
    # Con: if the process crashes, the task is lost. No retry, no status tracking.
    ```

    **Tier 2 — Job status tracking (recommended for this assignment)**
    ```python
    # POST /refresh → generate job_id → store in Redis → start background task
    # GET /refresh/status/{job_id} → return {status: pending|running|done|failed, updated: N}

    @router.post("/refresh", status_code=202)
    async def refresh_cryptocurrencies(background_tasks: BackgroundTasks):
        job_id = str(uuid.uuid4())
        await cache_set(f"refresh:job:{job_id}", {"status": "pending"}, ttl=300)
        background_tasks.add_task(_run_refresh, job_id)
        return {"job_id": job_id, "status": "accepted",
                "poll_url": f"/api/v1/cryptocurrencies/refresh/status/{job_id}"}

    @router.get("/refresh/status/{job_id}")
    async def refresh_status(job_id: str):
        job = await cache_get(f"refresh:job:{job_id}")
        if not job:
            raise NotFoundError("Job not found or expired")
        return job  # {status, updated_count, completed_at, error}
    ```

    **Tier 3 — Celery + Redis broker (production at scale)**
    ```python
    # tasks/refresh.py
    @celery.task(bind=True, max_retries=3, default_retry_delay=30)
    def refresh_coins_task(self):
        try:
            count = sync_refresh()  # sync version for Celery
            return {"updated": count}
        except CoinGeckoError as e:
            self.retry(exc=e)
    # Pro: persistent queue, retries, worker isolation, scheduled runs (beat)
    # Con: adds Redis as broker + Celery workers to infra
    ```

  - **Which to implement for this assignment**: Tier 2 — job status tracking.
    It demonstrates the async pattern cleanly, adds a polled status endpoint
    (realistic real-world pattern), and requires zero extra infra beyond Redis
    which we already have.

  - **Implementation steps**:
    - [ ] `POST /cryptocurrencies/refresh` → return `202 Accepted` + `job_id` immediately
    - [ ] `GET /cryptocurrencies/refresh/status/{job_id}` → poll job status from Redis
    - [ ] Background task updates Redis: `pending` → `running` → `done` / `failed`
    - [ ] On completion: store `{status, updated_count, completed_at, duration_ms}`
    - [ ] On failure: store `{status: "failed", error: "...", failed_at}`
    - [ ] Idempotency: if a refresh job is already `running`, return its `job_id` instead
          of starting a new one (prevents parallel refresh storms)
    - [ ] Unit tests: verify 202 returned immediately, background task called
    - [ ] Integration test: poll status until `done`, verify coins updated
    - [ ] Update Postman collection: seed step uses polling instead of fire-and-forget
    - [ ] Mention Celery as the next step for production scale in README/video

  - **Why this matters (mention in video)**:
    > "The current refresh endpoint is synchronous — the HTTP connection stays open
    > for 2 seconds while we wait for CoinGecko. I designed it as async with 202 Accepted
    > and job-status polling, which is the pattern used by every serious API that
    > triggers slow external work — AWS, Stripe, GitHub Actions all use this.
    > At scale this would move to Celery with a Redis broker so refresh jobs survive
    > process restarts and can be scheduled automatically — but FastAPI BackgroundTasks
    > is the right starting point before you have that operational overhead."

- [ ] **Database Optimization — Indexes & Query-Driven Schema Design**
  - **The problem**: defining fields in SQLAlchemy ORM is not enough. A senior engineer
    thinks about the actual queries that will run, and adds indexes that match the
    data access patterns — not as an afterthought, but at design time.

  - **Current state**: basic indexes exist on `users.email`, `cryptocurrencies.external_id`,
    `cryptocurrencies.symbol`. ✅ Missing: compound indexes for the actual query patterns.

  - **Query-driven index analysis**:

    | Endpoint | Query pattern | Required index |
    |---|---|---|
    | `GET /cryptocurrencies/:id/history` | `WHERE cryptocurrency_id = ? ORDER BY timestamp DESC` | Compound: `(cryptocurrency_id, timestamp DESC)` |
    | `GET /watchlist` | `WHERE user_id = ? ORDER BY added_at DESC` | Compound: `(user_id, added_at DESC)` |
    | `POST /auth/login` | `WHERE email = ?` | Single: `email` ✅ already exists |
    | `GET /cryptocurrencies?sort_by=market_cap_rank` | `ORDER BY market_cap_rank` | Single: `market_cap_rank` |
    | `GET /cryptocurrencies?sort_by=current_price` | `ORDER BY current_price` | Single: `current_price` |

  - **PriceHistory table — currently missing entirely**:
    ```python
    # The history endpoint currently fetches from CoinGecko every time.
    # A proper implementation stores price history in DB for offline access,
    # faster queries, and historical analysis beyond CoinGecko's free tier limits.

    class PriceHistory(Base):
        __tablename__ = "price_history"
        __table_args__ = (
            # Compound index — the most critical query is:
            # SELECT * FROM price_history
            # WHERE cryptocurrency_id = ? AND timestamp >= ?
            # ORDER BY timestamp DESC
            # Without this index: full table scan on millions of rows = API timeout
            Index("ix_price_history_coin_time",
                  "cryptocurrency_id", "timestamp",
                  postgresql_ops={"timestamp": "DESC"}),
            UniqueConstraint("cryptocurrency_id", "timestamp",
                             name="uq_price_history_coin_time"),
        )
        id:                uuid
        cryptocurrency_id: FK → cryptocurrencies.id
        timestamp:         DateTime (indexed)
        price:             Float
        volume_24h:        Float (nullable)
        market_cap:        Float (nullable)
    ```

  - **EXPLAIN ANALYZE — verify indexes are used**:
    ```sql
    -- Run this after adding indexes to confirm query plan uses index scan
    EXPLAIN ANALYZE
    SELECT * FROM price_history
    WHERE cryptocurrency_id = '...'
    ORDER BY timestamp DESC
    LIMIT 100;
    -- Should show: "Index Scan using ix_price_history_coin_time"
    -- NOT: "Seq Scan" (full table scan = missing index)
    ```

  - **Watchlist compound index** — already has `UniqueConstraint("user_id", "cryptocurrency_id")`
    which PostgreSQL backs with an implicit B-tree index. ✅ But `ORDER BY added_at DESC`
    needs an additional index if the watchlist grows large:
    ```python
    Index("ix_watchlist_user_time", "user_id", "added_at",
          postgresql_ops={"added_at": "DESC"})
    ```

  - **TimescaleDB upgrade path** (mention in video):
    > "For millions of price history rows, TimescaleDB turns this into a hypertable
    > with automatic time-based partitioning — the compound index + partitioning
    > together gives sub-10ms queries on billions of rows. That's the production
    > upgrade path from Postgres, with zero application code changes."

  - **Implementation steps**:
    - [ ] New Alembic migration: `PriceHistory` table with compound index
    - [ ] Compound index on `watchlist(user_id, added_at DESC)`
    - [ ] Single indexes on `cryptocurrencies.market_cap_rank` and `current_price`
    - [ ] Update `crypto_service.py` history method to read from DB first, fall back to CoinGecko
    - [ ] Seed script: populate `price_history` during `/refresh`
    - [ ] Add `EXPLAIN ANALYZE` test in README showing index scan vs seq scan
    - [ ] Comment in migration explaining WHY each index exists (query it serves)

- [ ] **Thundering Herd / Cache Stampede Prevention**
  - **The problem**: when a popular cache key expires (e.g. coin list TTL = 60s),
    all concurrent requests simultaneously get a cache miss and all race to fetch
    from DB/CoinGecko. With 1,000 concurrent users, that's 1,000 simultaneous
    CoinGecko API calls — which hits the rate limit, crashes the external API,
    and likely 429s your entire service.

  - **Current state**: basic cache-aside exists (get → miss → fetch → set). ❌ No stampede protection.

  - **Three strategies** (layered — implement all three for full protection):

    **Strategy 1 — Redis mutex (distributed lock)**
    ```python
    # Only the FIRST cache-missing request fetches. All others wait.
    # app/core/cache.py

    async def get_or_fetch_with_lock(key: str, fetch_fn, ttl: int):
        cached = await cache_get(key)
        if cached:
            return cached

        lock_key = f"lock:{key}"
        r = await get_redis()

        # Try to acquire lock (NX = only set if not exists, EX = expire in 5s)
        acquired = await r.set(lock_key, "1", nx=True, ex=5)

        if acquired:
            try:
                value = await fetch_fn()
                await cache_set(key, value, ttl=ttl)
                return value
            finally:
                await r.delete(lock_key)
        else:
            # Another request is fetching — wait briefly and return from cache
            for _ in range(10):
                await asyncio.sleep(0.1)
                cached = await cache_get(key)
                if cached:
                    return cached
            # Fallback: fetch directly (lock expired but cache still empty)
            return await fetch_fn()
    ```

    **Strategy 2 — Probabilistic early expiration (XFetch algorithm)**
    ```python
    # Instead of expiring at exactly TTL seconds, expire randomly BEFORE TTL
    # so different requests trigger refresh at different times — no stampede.
    # Probability of early refresh increases as TTL approaches.

    import math, random

    async def cache_get_xfetch(key: str, fetch_fn, ttl: int, beta: float = 1.0):
        r = await get_redis()
        data = await r.get(key)
        if data:
            item = json.loads(data)
            remaining_ttl = await r.ttl(key)
            # Early recompute if: -beta * delta * log(random()) > remaining_ttl
            delta = item.get("_fetch_duration", 0.1)
            if -beta * delta * math.log(random.random()) > remaining_ttl:
                # Proactively refresh before expiry (only this one request does it)
                value = await fetch_fn()
                await cache_set(key, value, ttl=ttl)
                return value
            return item["value"]
        # Cache miss — fetch normally
        value = await fetch_fn()
        await cache_set(key, {"value": value, "_fetch_duration": ...}, ttl=ttl)
        return value
    ```

    **Strategy 3 — Background refresh (proactive, never expires for users)**
    ```python
    # A background task refreshes the cache BEFORE it expires.
    # Users always read from cache — they never experience a miss.
    # Triggered by: APScheduler / asyncio.create_task on app startup

    # app/core/background_refresh.py
    async def schedule_coin_cache_refresh():
        while True:
            await asyncio.sleep(55)  # refresh every 55s, TTL is 60s
            try:
                coins = await fetch_from_db()
                await cache_set("coins:list:1:50:market_cap_rank", coins, ttl=60)
                logger.info("proactive cache refresh complete")
            except Exception as e:
                logger.warning("proactive cache refresh failed", error=str(e))
    # Coin data is always warm — no user ever triggers a cache miss
    ```

  - **Which to implement**:
    - Strategy 1 (mutex) → for coin detail and history (low-traffic, correct)
    - Strategy 3 (background refresh) → for coin list (high-traffic, most impactful)
    - Strategy 2 (XFetch) → mention in documentation/video as the academic gold standard

  - **Implementation steps**:
    - [ ] `app/core/cache.py` — add `get_or_fetch_with_lock()` using Redis `SET NX`
    - [ ] `app/core/background_refresh.py` — proactive refresh task for coin list
    - [ ] Wire background refresh into `app/main.py` lifespan (alongside gRPC server)
    - [ ] Replace cache-aside in `crypto_service.get_all()` with `get_or_fetch_with_lock()`
    - [ ] Unit tests: concurrent calls with mocked Redis → only one fetch call executes
    - [ ] k6 test: 1000 concurrent VUs hitting `/cryptocurrencies` at cache expiry moment
          → verify CoinGecko mock called exactly once, not 1000 times
    - [ ] Add `cache_stampede_prevented` counter metric

  - **Why this matters (mention in video)**:
    > "Cache stampede is the failure mode that takes down services at exactly the
    > wrong moment — when you have peak traffic. The Redis mutex pattern ensures
    > only one request races to the DB. The background refresh eliminates the
    > problem entirely for high-traffic endpoints: users never see a cache miss
    > because the cache is always being proactively warmed. Together, these patterns
    > are what separate a cache that works in demos from one that works at scale."

## Backlog

- [ ] **k6 results in CI** — parse k6 JSON output and post p99 summary as a PR comment
- [ ] **Swagger enhancements** — add response examples to OpenAPI schema for better Postman UX
- [ ] **DB connection pool metrics** — expose asyncpg pool size / checked-out connections
- [ ] **Health check depth** — extend `/health` to check DB + Redis connectivity (liveness vs readiness)
