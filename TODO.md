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

## Backlog
- [ ] **Integration tests** — commit the extensive test file (test_api_extensive.py was written locally)
- [ ] **k6 results in CI** — parse k6 JSON output and post p99 summary as a PR comment
- [ ] **Swagger enhancements** — add response examples to OpenAPI schema for better Postman UX
- [ ] **DB connection pool metrics** — expose asyncpg pool size / checked-out connections
- [ ] **Structured logging** — replace print/logging with structlog (JSON output for CloudWatch Logs Insights)
- [ ] **Health check depth** — extend `/health` to check DB + Redis connectivity (liveness vs readiness)
- [ ] **Delete `/watchlist` endpoint** — currently missing from Postman env var flow (uses `watchlist_coin_id`)
