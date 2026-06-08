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

## Backlog

- [ ] **k6 results in CI** — parse k6 JSON output and post p99 summary as a PR comment
- [ ] **Swagger enhancements** — add response examples to OpenAPI schema for better Postman UX
- [ ] **DB connection pool metrics** — expose asyncpg pool size / checked-out connections
- [ ] **Structured logging** — replace print/logging with structlog (JSON output for CloudWatch Logs Insights)
- [ ] **Health check depth** — extend `/health` to check DB + Redis connectivity (liveness vs readiness)
