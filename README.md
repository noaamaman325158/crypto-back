# Crypto Dashboard API

A production-grade cryptocurrency dashboard backend built with **FastAPI**, **PostgreSQL**, **Redis**, and **Claude AI**.

## Architecture Highlights

> **Dual-protocol AI endpoint** — The `/insight` service is exposed over both REST (port 8000) and gRPC (port 50051) from the same process. This mirrors the pattern used in Dataminr's AI services (e.g. `agentic-search`): one service, two transports, zero logic duplication. gRPC server reflection is enabled so clients can introspect available methods at runtime without a `.proto` file.

- **Async-first**: SQLAlchemy 2.0 async, asyncpg, httpx — no blocking I/O
- **Layered architecture**: Router → Service → Repository — each layer has one responsibility
- **Auth**: JWT (PyJWT, user-facing) + API Keys (service-to-service) + RBAC roles
- **Caching**: Redis cache-aside pattern for coin data (60s TTL) and AI insights (1h TTL)
- **IaC**: Full Terraform on AWS (ECS Fargate + RDS + ElastiCache) + LocalStack for local dev
- **CI/CD**: GitHub Actions with 6-layer security gates — all before any build runs
- **AI**: Claude API analyzes 30-day price history and returns trend insights
- **Dual-protocol**: REST (`:8000`) + gRPC (`:50051`) served from one process — same business logic, two transports
- **Zero CVEs**: All dependencies audited with pip-audit; python-jose replaced by PyJWT to resolve pyasn1 conflict

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.136 + Uvicorn |
| Database | PostgreSQL 16 (async via asyncpg + SQLAlchemy 2.0) |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic |
| Auth | PyJWT 2.13 + bcrypt (passlib) |
| Cache | Redis 7 |
| Rate Limiting | slowapi |
| External Data | CoinGecko API |
| AI | Anthropic Claude API (claude-sonnet-4-6) |
| gRPC | grpcio 1.68 + server reflection |
| Infra | AWS ECS Fargate + RDS PostgreSQL + ElastiCache via Terraform |
| Local AWS emulation | LocalStack 3.4 |
| Container | Distroless Python runtime (208MB → 58MB, ~0 CVEs) |
| CI/CD | GitHub Actions (supply-chain hardened) |
| Dependency locking | pip-compile (requirements.lock) |

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
- Python 3.10+

### With Docker Compose (recommended)

```bash
git clone https://github.com/noaamaman325158/crypto-back.git
cd crypto-back
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and INTERNAL_API_KEY at minimum
docker-compose up
```

| Service | URL |
|---|---|
| REST API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| gRPC | localhost:50051 |
| LocalStack (AWS emulation) | http://localhost:4566 |

### Without Docker

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.lock   # install from lockfile for reproducibility

# Start Postgres and Redis separately, then:
alembic upgrade head
uvicorn app.main:app --reload
```

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | — | Register new user |
| POST | `/api/v1/auth/login` | — | Login, returns JWT + refresh token |
| POST | `/api/v1/auth/refresh` | — | Rotate access token |
| GET | `/api/v1/cryptocurrencies` | — | Paginated coin list (sortable) |
| GET | `/api/v1/cryptocurrencies/:id` | — | Single coin detail |
| POST | `/api/v1/cryptocurrencies/refresh` | `X-API-Key` | Pull fresh data from CoinGecko |
| GET | `/api/v1/cryptocurrencies/:id/history` | — | Price history (7/30/90 days) |
| GET | `/api/v1/cryptocurrencies/:id/insight` | JWT | Claude AI trend analysis |
| GET | `/api/v1/watchlist` | JWT | Get user's watchlist |
| POST | `/api/v1/watchlist` | JWT | Add coin to watchlist |
| DELETE | `/api/v1/watchlist/:id` | JWT | Remove coin from watchlist |
| GET | `/health` | — | Health check |

## API Usage

### 1. Seed cryptocurrency data
```bash
# Use the value of INTERNAL_API_KEY from your .env
curl -X POST http://localhost:8000/api/v1/cryptocurrencies/refresh \
  -H "X-API-Key: $INTERNAL_API_KEY"
```

### 2. Register and login
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
# → copy access_token from response
export TOKEN=<access_token>
```

### 3. Browse coins
```bash
curl "http://localhost:8000/api/v1/cryptocurrencies?per_page=10&sort_by=market_cap_rank"
curl "http://localhost:8000/api/v1/cryptocurrencies/<uuid>"
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

## gRPC API

The AI insight endpoint is also available over gRPC on port `50051`.

Server reflection is enabled — use `grpcurl` without a `.proto` file:

```bash
# Install grpcurl: brew install grpcurl

# Discover available services
grpcurl -plaintext localhost:50051 list

# Describe the InsightService
grpcurl -plaintext localhost:50051 describe crypto.insight.v1.InsightService

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

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Postman Collection**: `postman/collection.json` — import with `postman/env.local.json`

### Run Postman collection as integration tests (Newman)
```bash
npx newman run postman/collection.json -e postman/env.local.json
```

The Postman collection includes inline test scripts on every request — it is both documentation and a living test suite.

## Running Tests

```bash
# Unit tests (no DB required — all dependencies mocked)
pytest tests/unit/ -v

# Integration tests (requires local Postgres + Redis via docker-compose)
pytest tests/integration/ -v --cov=app

# All tests
pytest -v --cov=app
```

### Test structure

| Layer | Location | Needs DB? |
|---|---|---|
| Unit | `tests/unit/` | No — services, JWT, security logic mocked |
| Integration | `tests/integration/` | Yes — real Postgres + Redis |
| E2E | `postman/collection.json` | Yes — full live server via Newman |

## Dependency Management

Dependencies are fully pinned via `requirements.lock` (generated by pip-compile):

```bash
# Add a new dependency
echo "newpackage==1.2.3" >> requirements.txt
pip-compile requirements.txt --output-file=requirements.lock
git add requirements.txt requirements.lock
```

The CI `lockfile-check` job enforces that `requirements.lock` is always in sync with `requirements.txt`. Builds fail if they diverge.

## Local AWS Emulation (LocalStack)

`docker-compose up` starts LocalStack alongside the app. AWS SDK calls (SSM, ECR, etc.) are routed to `http://localhost:4566` automatically.

To run Terraform against LocalStack:
```bash
./scripts/tf-localstack.sh plan    # preview what would be created
./scripts/tf-localstack.sh apply   # provision locally

# Or via Make:
make tf-localstack-plan
make tf-localstack-apply
```

## Deployment (AWS)

### Prerequisites
- AWS CLI configured with appropriate permissions
- Terraform >= 1.6
- Docker

### Provision infrastructure

```bash
cd infra
terraform init

terraform plan \
  -var="image_tag=<git-sha>" \
  -var="db_password=<secret>" \
  -var="secret_key=<secret>" \
  -var="internal_api_key=<secret>" \
  -var="anthropic_api_key=<secret>"

terraform apply
```

Resources created: VPC, public/private subnets, ECS Fargate cluster, ALB, RDS PostgreSQL (encrypted, with CloudWatch logging), ElastiCache Redis (encrypted at rest + in transit), ECR repository, SSM Parameter Store secrets, IAM roles with OIDC for GitHub Actions.

The ALB DNS is output as `app_url`. Alembic migrations run automatically on container startup.

### CI/CD Pipeline

The pipeline runs in strict stages — **no build starts until every security gate passes**.

**Stage 1 — Security gates (all parallel):**

| Job | Tool | What it catches |
|---|---|---|
| `pipeline-scan` | [poutine](https://github.com/boostsecurityio/poutine) | Injection vectors, dangerous triggers, unpinned actions in workflows |
| `secret-scan` | [TruffleHog](https://github.com/trufflesecurity/trufflehog) | API keys / credentials across full git history (verified only) |
| `sast` | [Semgrep](https://semgrep.dev) | OWASP Top 10, JWT misconfig, FastAPI-specific patterns |
| `sca` | pip-audit | CVEs in all deps including transitive |
| `lockfile-check` | pip-tools | `requirements.lock` out of sync with `requirements.txt` |
| `iac-validate` | Terraform + LocalStack | Infra config errors without touching real AWS |

**Stage 2 — Code quality (parallel, after Stage 1):**
- `lint` — Ruff
- `type-check` — mypy
- `unit-test` — pytest (no DB)

**Stage 3 — Integration tests:**
- pytest against real Postgres + Redis (Docker service containers)

**Stage 4 — E2E tests:**
- Newman runs full Postman collection against a live server

**Stage 5 — Build & deploy (main branch only):**
- Docker image built (multi-stage, distroless runtime)
- Tagged with commit SHA — never `latest`
- Pushed to ECR
- ECS service updated (zero-downtime rolling deploy)

**Supply chain hardening:**
- All GitHub Actions pinned to immutable 40-char commit SHAs (not version tags)
- AWS credentials via OIDC — no `AWS_ACCESS_KEY_ID` stored in GitHub Secrets
- Docker images immutably tagged with git SHA
- `pip-audit` scans transitive dependencies for CVEs on every push

Required GitHub Secrets: `AWS_OIDC_ROLE_ARN`, `AWS_REGION`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`, `ANTHROPIC_API_KEY`

## Key Design Decisions

### Why PostgreSQL over MongoDB?
Crypto data is relational: users ↔ watchlists ↔ coins. Relational integrity, `ON CONFLICT DO UPDATE` upserts for coin refresh, and range queries on price history make Postgres the right tool. Trade-off: at billions of price history rows, TimescaleDB (a Postgres extension for time-series) would be the natural upgrade — no migration required, same driver.

### Why Redis?
Without caching, every `GET /cryptocurrencies` hits Postgres even though coin data changes once per minute at most. Redis is shared across all ECS task instances (unlike in-process dicts which don't survive restarts or scale out), and doubles as the rate-limit counter backend via slowapi. AI insights are cached for 1 hour — Claude API calls are expensive and the insight doesn't change minute-to-minute. Cache invalidation is explicit: `/refresh` deletes the coin list cache key immediately.

### Why JWT + API Keys (two auth layers)?
Not all endpoints are user-facing. `/refresh` is a privileged operation called by schedulers or internal services — it uses `X-API-Key` header auth (validated with `hmac.compare_digest` to prevent timing attacks). User endpoints use short-lived JWTs (15 min) with refresh token rotation stored in the DB for revocation. In production at scale: service-to-service would use AWS IAM + SigV4 signing or mTLS — mentioned in code comments as the upgrade path.

### Why PyJWT over python-jose?
`python-jose` pins `pyasn1<0.5.0` which conflicts with the CVE fix for pyasn1 (`>=0.6.3`). PyJWT is the actively maintained successor with no pyasn1 dependency and a minimal API surface change (`from jose import jwt` → `import jwt`).

### Why distroless runtime image?
The production Docker image uses a multi-stage build: `python:3.10-slim-bookworm` for the build stage (has pip, gcc for compiling asyncpg C extensions), and `gcr.io/distroless/python3-debian12` for the runtime stage. Result: 208MB → 58MB, near-zero CVEs, no shell (attacker who gets RCE can't drop into `/bin/sh`). Trade-off: `docker exec` debugging requires ephemeral debug containers.

### Why dual-protocol (REST + gRPC)?
The AI insight endpoint is served over both REST (`/api/v1/cryptocurrencies/{id}/insight`) and gRPC (`crypto.insight.v1.InsightService/GetInsight`) from the same process. Both transports call identical business logic — zero duplication. This mirrors the pattern used in Dataminr's AI microservices (agentic-search, embedding services): one service definition in `.proto`, two transports. At Dataminr's scale (30+ AI services), the REST translation is extracted into a sidecar gateway (AGL) so the protocol layer is infrastructure, not application code. For a single service, in-process is the right trade-off.

### Supply Chain Security
GitHub Actions are pinned to full 40-char commit SHAs (tags are mutable — a compromised maintainer can point a tag at malicious code). AWS credentials use OIDC, eliminating long-lived `AWS_ACCESS_KEY_ID` secrets from GitHub. Docker images are tagged with git commit SHA — deployments are reproducible and rollback is a one-line change.

The pipeline itself is scanned on every push by **poutine** — the same static analysis engine that powers [SmokedMeat](https://github.com/boostsecurityio/smokedmeat), a CI/CD red team framework. If a future PR introduces a dangerous trigger or an unpinned action, the build fails before any code runs.

To manually red-team the pipeline:
```bash
git clone https://github.com/boostsecurityio/smokedmeat.git
cd smokedmeat
make quickstart
# Target: this repo | Expected: no exploitable workflows found
```
