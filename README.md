# Crypto Dashboard API

A production-grade cryptocurrency dashboard backend built with **FastAPI**, **PostgreSQL**, **Redis**, and **Claude AI**.

## Architecture Highlights

> **Push-based data pipeline** — CoinGecko is accessed exclusively by a scheduled background worker every 5 minutes. User-facing APIs read from PostgreSQL (system of record) → Redis (write-through cache). CoinGecko outages do not affect read traffic. Every coin response includes `data_age_seconds` so clients know exactly how fresh the data is.

> **Dual-protocol AI endpoint** — The `/insight` service is exposed over both REST (port 8000) and gRPC (port 50051) from the same process. This mirrors the pattern used in Dataminr's AI services: one service, two transports, zero logic duplication. gRPC server reflection is enabled so clients can introspect available methods at runtime without a `.proto` file.

- **Async-first**: SQLAlchemy 2.0 async, asyncpg, httpx — no blocking I/O
- **Layered architecture**: Router → Service → Repository — each layer has one responsibility
- **Provider abstraction**: `CryptoProvider` ABC decouples all services from CoinGecko — swap providers by changing one factory function
- **Auth**: JWT (PyJWT, user-facing) + API Keys (service-to-service) + RBAC roles
- **Background jobs**: APScheduler worker process refreshes 500 coins every 5 minutes with distributed Redis lock, write-through cache, dead-letter queue on failure, and 90-day history purge
- **Idempotency**: `Idempotency-Key` header + Redis 24h TTL on mutating endpoints
- **Caching**: Redis stampede-safe cache (`SET NX` distributed lock), write-through from worker, 60s TTL on coin data, 1h on AI insights
- **Circuit breaker**: CLOSED/OPEN/HALF_OPEN state machine wrapping CoinGecko and Claude API calls
- **IaC**: Full Terraform on AWS (ECS Fargate + RDS + ElastiCache) + LocalStack for local dev
- **CI/CD**: GitHub Actions with 8-stage pipeline including coverage reporting and image scanning
- **AI**: Claude API analyzes 30-day price history and returns trend insights
- **Dual-protocol**: REST (`:8000`) + gRPC (`:50051`) served from one process
- **Observability**: Prometheus metrics + Grafana dashboards + Alertmanager with 12 alert rules
- **Zero CVEs**: All dependencies audited with pip-audit; python-jose replaced by PyJWT

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.136 + Uvicorn |
| Database | PostgreSQL 16 (async via asyncpg + SQLAlchemy 2.0) |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic (sync psycopg2 driver at startup) |
| Auth | PyJWT 2.13 + bcrypt (passlib) |
| Cache | Redis 7 (stampede-safe, write-through) |
| Rate Limiting | slowapi |
| Background scheduler | APScheduler 3.10 (separate worker process) |
| External Data | CoinGecko API (via `CryptoProvider` abstraction) |
| AI | Anthropic Claude API (claude-sonnet-4-6) |
| gRPC | grpcio 1.68 + server reflection |
| Logging | structlog (JSON in prod, colored console in dev) |
| Metrics | Prometheus (`prometheus-fastapi-instrumentator` + `prometheus_client`) |
| Dashboards | Grafana 11.4 (auto-provisioned) |
| Alerting | Alertmanager 0.27 (Slack routing, inhibit rules) |
| Infra | AWS ECS Fargate + RDS PostgreSQL + ElastiCache via Terraform |
| Local AWS emulation | LocalStack 3.4 |
| Container | Distroless Python 3.11 runtime (208MB → 58MB, ~0 CVEs) |
| CI/CD | GitHub Actions (supply-chain hardened) |
| Dependency locking | pip-compile (requirements.lock, Python 3.11) |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | Yes | JWT signing secret (random 32+ chars) |
| `INTERNAL_API_KEY` | Yes | Service-to-service API key for `/refresh` endpoint |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for AI insights |
| `REDIS_URL` | Yes | Redis connection string |
| `CORS_ORIGINS` | No | JSON list of allowed origins (default: localhost only) |
| `COINGECKO_API_KEY` | No | CoinGecko API key (increases rate limits) |
| `ENVIRONMENT` | No | `development` or `production` (default: `development`) |

## Run Locally

### Prerequisites
- Docker + Docker Compose
- Python 3.11+

### With Docker Compose (recommended)

```bash
git clone https://github.com/noaamaman325158/crypto-back.git
cd crypto-back
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and INTERNAL_API_KEY at minimum
docker-compose up -d
```

| Service | URL |
|---|---|
| REST API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Prometheus metrics (API) | http://localhost:8000/metrics |
| Prometheus metrics (worker) | http://localhost:9091 |
| Prometheus UI | http://localhost:9090 |
| Grafana dashboards | http://localhost:3001 (admin / admin) |
| Alertmanager | http://localhost:9093 |
| gRPC | localhost:50051 |
| LocalStack (AWS emulation) | http://localhost:4566 |

The **worker** container starts alongside the app and runs its first refresh immediately. After ~1 second, 500 coins are in PostgreSQL and Redis — no manual seeding required.

### Without Docker

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.lock

# Start Postgres and Redis separately, then:
alembic upgrade head
uvicorn app.main:app --reload

# In a second terminal — start the background refresh worker:
python -m app.worker.refresh_job
```

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | — | Register new user |
| POST | `/api/v1/auth/login` | — | Login, returns JWT + refresh token |
| POST | `/api/v1/auth/refresh` | — | Rotate access token |
| GET | `/api/v1/cryptocurrencies` | — | Paginated coin list (sortable) |
| GET | `/api/v1/cryptocurrencies/top-movers` | — | Top gainers + losers by 24h change |
| GET | `/api/v1/cryptocurrencies/:id` | — | Single coin detail (includes `data_age_seconds`) |
| POST | `/api/v1/cryptocurrencies/refresh` | `X-API-Key` | On-demand refresh (202, async, idempotent) |
| GET | `/api/v1/cryptocurrencies/:external_id/history` | — | Price history from DB (7/30/90 days) |
| GET | `/api/v1/cryptocurrencies/:external_id/insight` | JWT | Claude AI trend analysis |
| GET | `/api/v1/watchlist` | JWT | Get user's watchlist |
| POST | `/api/v1/watchlist` | JWT | Add coin to watchlist (idempotent) |
| DELETE | `/api/v1/watchlist/:id` | JWT | Remove coin from watchlist |
| GET | `/metrics` | — | Prometheus metrics scrape endpoint |
| GET | `/health` | — | Deep health check (DB + Redis latency) |

## Data Freshness

Every coin response includes `data_age_seconds` — the number of seconds since that coin was last refreshed by the worker:

```json
{
  "external_id": "bitcoin",
  "current_price": 63687.0,
  "data_age_seconds": 42,
  ...
}
```

The worker refreshes all 500 coins every 5 minutes. If `data_age_seconds` exceeds 600, the `CoinDataStale` Prometheus alert fires. Price history (`/history`) is served entirely from the `price_history` PostgreSQL table — no CoinGecko call at request time.

## Background Worker

The refresh worker runs as a **separate process** from the FastAPI app, sharing only the DB and Redis:

```
CoinGecko
    │
    ▼
app/worker/refresh_job.py  (APScheduler, every 5 min)
    │  ├── Distributed Redis lock (prevents overlap on slow runs)
    │  ├── Paginated fetch: 2 pages × 250 coins
    │  ├── Upsert → PostgreSQL (system of record)
    │  ├── Append → price_history table (one row per coin per run)
    │  ├── Write-through → Redis (TTL=310s, keys: coins:detail:*)
    │  ├── Invalidate → coins:list:*, coins:top_movers:*
    │  ├── Dead-letter → refresh_dead_letter table (after 3 retries)
    │  └── Purge → price_history rows older than 90 days
    │
    ▼
FastAPI (reads Redis → PostgreSQL only, never calls CoinGecko)
```

Worker exposes its own Prometheus metrics on `:9091`:
- `crypto_refresh_last_success_timestamp_seconds` — Unix timestamp of last successful run
- `crypto_refresh_coins_updated_last_run` — coins upserted in the most recent run
- `crypto_refresh_duration_seconds` — wall-clock time of last run
- `crypto_data_age_seconds` — seconds since last successful refresh (updated every 30s)
- `crypto_refresh_failures_total` — batches written to dead-letter queue

## Idempotency

Mutating endpoints accept an optional `Idempotency-Key` header. Sending the same key twice within the TTL window returns the same result without executing the operation again:

```bash
curl -X POST http://localhost:8000/api/v1/cryptocurrencies/refresh \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  -H "Idempotency-Key: $(uuidgen)"
# → 202 (scheduled)

# Same key again within 30 seconds:
# → 202 (deduplicated, no second CoinGecko call)
```

TTL: 30 seconds on `/refresh`, 24 hours on `/watchlist`.

## Circuit Breaker

CoinGecko and Claude API calls are wrapped in a circuit breaker with three states:

| State | Behaviour |
|---|---|
| CLOSED | Normal operation — failures increment counter |
| OPEN | All calls rejected immediately with `503` — no network I/O |
| HALF_OPEN | One probe call allowed — success closes, failure re-opens |

Thresholds: CoinGecko opens after 5 failures (30s recovery), Claude opens after 3 failures (60s recovery).

## API Usage

### 1. Data is seeded automatically
The worker runs on startup — within ~1 second of `docker-compose up`, 500 coins are available. No manual seeding required. To trigger an immediate on-demand refresh:

```bash
curl -X POST http://localhost:8000/api/v1/cryptocurrencies/refresh \
  -H "X-API-Key: $INTERNAL_API_KEY"
# → 202 Accepted (refresh runs in background)
```

### 2. Register and login
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
export TOKEN=<access_token>
```

### 3. Browse coins
```bash
# Paginated list
curl "http://localhost:8000/api/v1/cryptocurrencies?per_page=10&sort_by=market_cap_rank"

# Top movers (gainers + losers by 24h change)
curl "http://localhost:8000/api/v1/cryptocurrencies/top-movers?limit=5"

# Single coin (includes data_age_seconds)
curl "http://localhost:8000/api/v1/cryptocurrencies/<uuid>"

# Price history from DB (no external call)
curl "http://localhost:8000/api/v1/cryptocurrencies/bitcoin/history?days=30"
```

### 4. Manage watchlist
```bash
curl -X POST http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cryptocurrency_id": "<coin_uuid>"}'

curl http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer $TOKEN"

curl -X DELETE http://localhost:8000/api/v1/watchlist/<coin_uuid> \
  -H "Authorization: Bearer $TOKEN"
```

### 5. AI insight (REST)
```bash
curl "http://localhost:8000/api/v1/cryptocurrencies/bitcoin/insight" \
  -H "Authorization: Bearer $TOKEN"
```

## Observability

The app ships a full local observability stack. Prometheus scrapes both the API (`:8000/metrics`) and the worker (`:9091`) every 15s. Grafana auto-provisions the datasource and dashboard with no manual setup.

### Starting the stack

```bash
docker-compose up -d
```

Open Grafana at http://localhost:3001 (admin / admin).

### Metrics collected

| Category | Metrics |
|---|---|
| HTTP | Request rate, p95 latency, in-flight requests |
| Cache | `cache_hits_total`, `cache_misses_total` (labelled by `cache_key_prefix`) |
| Auth | `auth_attempts_total{result}`, `token_refresh_total{result}` |
| CoinGecko | `coingecko_requests_total`, `coingecko_latency_seconds`, `coingecko_errors_total` |
| AI insights | `ai_insight_requests_total{source}`, `ai_insight_latency_seconds` |
| Watchlist | `watchlist_operations_total{operation, result}` |
| Pipeline | `crypto_refresh_last_success_timestamp_seconds`, `crypto_data_age_seconds`, `crypto_refresh_coins_updated_last_run`, `crypto_refresh_duration_seconds`, `crypto_refresh_failures_total` |
| DB pool | `crypto_db_pool_size`, `crypto_db_pool_checked_out`, `crypto_db_pool_overflow` |
| Circuit breaker | State transitions tracked via `coingecko_errors_total` |

### Alerting (Alertmanager)

12 alert rules across 5 groups, routed to Slack:

| Alert | Threshold | Severity |
|---|---|---|
| `ServiceDown` | app unreachable > 1m | critical |
| `HighErrorRate` | 5xx rate > 5% for 2m | critical |
| `HighLatency` | p95 > 1s for 5m | warning |
| `HighAuthFailureRate` | >30% login failures for 5m | warning |
| `TokenRefreshRevoked` | >0.1/s revoked refreshes for 5m | warning |
| `LowCacheHitRate` | hit rate < 50% for 10m | warning |
| `CoinGeckoErrors` | >0.05/s errors for 5m | warning |
| `CoinGeckoHighLatency` | p95 > 5s for 5m | warning |
| `CoinDataStale` | `data_age_seconds` > 600 for 2m | warning |
| `CoinDataCriticallyStale` | `data_age_seconds` > 1800 for 1m | critical |
| `RefreshWorkerDown` | metric absent for 10m | critical |
| `RefreshBatchFailures` | any dead-letter writes in 30m | warning |

Warning alerts route to `#alerts`. Critical alerts route to `#critical`. Warning inhibited by critical on the same instance.

## Structured Logging

All logs are emitted via `structlog`. In development, colored console output. In production (`ENVIRONMENT=production`), newline-delimited JSON — one object per log line, ready for CloudWatch Logs Insights or Datadog.

Every request binds a short `request_id` to the context:

```json
{"method": "GET", "path": "/api/v1/cryptocurrencies", "status_code": 200, "duration_ms": 12.4, "request_id": "a3f2b1c4", "event": "request", "level": "info", "timestamp": "2026-06-11T19:43:26Z"}
```

Worker logs use the same format:

```json
{"event": "refresh_completed", "total": 500, "duration_s": 0.73, "level": "info", "timestamp": "2026-06-11T19:43:27Z"}
```

## Health Check

`GET /health` performs a deep check — both DB and Redis are probed on every call:

```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok", "latency_ms": 1.2},
    "redis":    {"status": "ok", "latency_ms": 0.4}
  }
}
```

Returns `200` when all checks pass, `503` when any dependency is unreachable. The `status` field is `"ok"` or `"degraded"` — never an error string, so clients can branch on a single field.

## gRPC API

The AI insight endpoint is also available over gRPC on port `50051`.

```bash
# Discover available services
grpcurl -plaintext localhost:50051 list

# Call GetInsight
grpcurl -plaintext \
  -d '{"coin_id": "bitcoin", "days": 30}' \
  localhost:50051 \
  crypto.insight.v1.InsightService/GetInsight
```

To regenerate stubs after editing `proto/crypto/insight/v1/insight.proto`:
```bash
make proto
```

## API Documentation

- **Swagger UI**: http://localhost:8000/docs — all schemas include `json_schema_extra` examples
- **ReDoc**: http://localhost:8000/redoc
- **Postman Collection**: `postman/collection.json` — import with `postman/env.local.json`

```bash
npx newman run postman/collection.json -e postman/env.local.json
```

## Running Tests

```bash
# Unit tests (no DB required)
pytest tests/unit/ -v

# Integration tests (requires Postgres + Redis)
pytest tests/integration/ -v --cov=app

# All tests with combined coverage
pytest -v --cov=app
```

### Test structure

| Layer | Location | Needs DB? |
|---|---|---|
| Unit | `tests/unit/` | No — services, JWT, security logic mocked |
| Integration | `tests/integration/` | Yes — real Postgres + Redis |
| E2E | `postman/collection.json` | Yes — full live server via Newman |

### Performance tests (k6)

```bash
k6 run k6/coins.test.js
k6 run k6/auth.test.js
k6 run k6/watchlist.test.js
```

| Scenario | Description |
|---|---|
| Smoke | 1 VU, 30s — verifies correctness at minimal load |
| Load | 10 VUs, 2 min ramp-up — baseline performance |
| Stress | Ramps to 50 VUs — finds the breaking point |

Rate limits are multiplied by 100x when `ENVIRONMENT != production` so k6 tests are not throttled by per-minute caps.

## Dependency Management

```bash
# Add a new dependency
echo "newpackage==1.2.3" >> requirements.txt
pip-compile requirements.txt --output-file=requirements.lock --no-strip-extras
git add requirements.txt requirements.lock
```

Always regenerate `requirements.lock` with Python 3.11 (or via `python:3.11-slim-bookworm` Docker container) to avoid backport packages.

## Local AWS Emulation (LocalStack)

```bash
./scripts/tf-localstack.sh plan
./scripts/tf-localstack.sh apply
```

## Deployment (AWS)

```bash
cd infra
terraform init
terraform apply \
  -var="image_tag=<git-sha>" \
  -var="db_password=<secret>" \
  -var="secret_key=<secret>" \
  -var="internal_api_key=<secret>" \
  -var="anthropic_api_key=<secret>"
```

Resources created: VPC, ECS Fargate cluster, ALB, RDS PostgreSQL (encrypted), ElastiCache Redis (encrypted), ECR, SSM Parameter Store secrets, IAM roles with OIDC. Alembic migrations run automatically on container startup.

### CI/CD Pipeline

**Stage 1 — Security gates (parallel):** poutine (pipeline injection), TruffleHog (secrets), Semgrep (SAST), pip-audit (SCA), lockfile-check, Terraform validate

**Stage 2 — Code quality (parallel):** Ruff (lint), mypy (type-check), pytest unit tests

**Stage 3 — Integration tests:** pytest against real Postgres + Redis

**Stage 4 — Coverage:** combines unit + integration artifacts, enforces `--fail-under=70`, uploads to Codecov

**Stage 5 — E2E:** Newman runs full Postman collection

**Stage 6 — Build:** Docker image (multi-stage, distroless), tagged with commit SHA, pushed to ECR

**Stage 7 — Image scan:** Trivy CVE scan, results to GitHub Security tab (SARIF)

**Stage 8 — Deploy (main only):** ECS rolling deploy, zero downtime

**Supply chain hardening:** all Actions pinned to 40-char commit SHAs, AWS via OIDC (no long-lived keys), images tagged by git SHA.

## Key Design Decisions

### Push-based data pipeline (no request-time provider calls)
User-facing APIs never call CoinGecko. The scheduled worker owns all CoinGecko traffic. This eliminates CoinGecko's SLA from the API's latency profile and allows the system to serve reads during CoinGecko outages. Trade-off: data is always up to N minutes stale — `data_age_seconds` in every response makes this explicit. The `RefreshWorkerDown` alert fires if the worker stops reporting within 10 minutes.

### Provider abstraction (`CryptoProvider` ABC)
All services depend on `app.providers.base.CryptoProvider`, not `CoinGeckoProvider` directly. To switch data sources, change `get_crypto_provider()` in `app/providers/coingecko.py`. The circuit breaker and metrics are attached at the provider layer — a new provider inherits them automatically.

### Idempotency via Redis
`POST /refresh` and `POST /watchlist` accept `Idempotency-Key`. The key is stored in Redis with a short TTL. Duplicate requests within the window return the same status code without side effects — safe to retry on network failures without triggering duplicate CoinGecko calls or duplicate DB writes.

### Cache stampede prevention
`cache_get_or_set()` uses Redis `SET NX` to acquire a distributed lock before calling the factory. Only one coroutine computes the value on a cache miss — all others wait and read the populated key. Prevents a cold-cache thundering herd from amplifying into N simultaneous DB queries.

### Why distroless runtime image?
`python:3.11-slim-bookworm` for the build stage (pip, gcc for asyncpg C extensions), `gcr.io/distroless/python3-debian12` for runtime. Result: 208MB → 58MB, near-zero CVEs, no shell. The distroless ENTRYPOINT is `/usr/bin/python3.11` — `CMD` provides only arguments (`["-m", "uvicorn", ...]`), not the interpreter path. The worker uses the same image with `command: ["-m", "app.worker.refresh_job"]`.

### Why sync psycopg2 for Alembic?
Alembic's `command.upgrade()` is synchronous. Running it inside an async lifespan blocks the event loop. Fix: `alembic/env.py` uses a psycopg2 engine, and `main.py` runs migrations in `loop.run_in_executor(None, _migrate)`.

### Why PyJWT over python-jose?
`python-jose` pins `pyasn1<0.5.0` which conflicts with CVE fix `>=0.6.3`. PyJWT is the maintained successor with no pyasn1 dependency.

### Supply chain security
All GitHub Actions pinned to 40-char commit SHAs (mutable tags are a supply chain attack vector). AWS credentials via OIDC — no `AWS_ACCESS_KEY_ID` in GitHub Secrets. Pipeline scanned on every push by **poutine**.
