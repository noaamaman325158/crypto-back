# Crypto Dashboard API

A production-grade cryptocurrency dashboard backend built with **FastAPI**, **PostgreSQL**, **Redis**, and **Claude AI**.

## Architecture Highlights

> **Dual-protocol AI endpoint** — The `/insight` service is exposed over both REST (port 8000) and gRPC (port 50051) from the same process. This mirrors the pattern used in Dataminr's AI services (e.g. `agentic-search`): one service, two transports, zero logic duplication. gRPC server reflection is enabled so clients can introspect available methods at runtime without a `.proto` file.

- **Async-first**: SQLAlchemy 2.0 async, asyncpg, httpx — no blocking I/O
- **Layered architecture**: Router → Service → Repository — each layer has one responsibility
- **Auth**: JWT (user-facing) + API Keys (service-to-service) + RBAC roles
- **Caching**: Redis cache-aside pattern for coin data (60s TTL) and AI insights (1h TTL)
- **IaC**: Full Terraform on AWS (ECS Fargate + RDS + ElastiCache)
- **CI/CD**: GitHub Actions with 5-layer security gates — poutine (pipeline SAST), TruffleHog (secrets), Semgrep (SAST), pip-audit (SCA), Terraform + LocalStack (IaC) — all before any build runs
- **AI**: Claude API analyzes 30-day price history and returns trend insights
- **Dual-protocol**: REST (`:8000`) + gRPC (`:50051`) served from one process — same business logic, two transports

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL 16 (async via asyncpg) |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Cache | Redis 7 |
| External Data | CoinGecko API |
| AI | Anthropic Claude API |
| Infra | AWS ECS Fargate + RDS + ElastiCache via Terraform |
| CI/CD | GitHub Actions |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | Yes | JWT signing secret (random 32+ chars) |
| `INTERNAL_API_KEY` | Yes | Service-to-service API key for `/refresh` |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for AI insights |
| `REDIS_URL` | Yes | Redis connection string |
| `COINGECKO_API_KEY` | No | CoinGecko API key (increases rate limits) |
| `ENVIRONMENT` | No | `development` or `production` |

## Run Locally

### Prerequisites
- Docker + Docker Compose
- Python 3.10+

### With Docker Compose (recommended)

```bash
git clone <repo>
cd crypto_back
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
docker-compose up
```

API available at `http://localhost:8000`  
Swagger UI at `http://localhost:8000/docs`

### Without Docker

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start Postgres and Redis separately, then:
alembic upgrade head
uvicorn app.main:app --reload
```

## API Usage

### 1. Seed cryptocurrency data
```bash
curl -X POST http://localhost:8000/api/v1/cryptocurrencies/refresh \
  -H "X-API-Key: dev-internal-key"
```

### 2. Register and login
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
# → copy access_token
```

### 3. Browse coins
```bash
curl http://localhost:8000/api/v1/cryptocurrencies?per_page=10
curl http://localhost:8000/api/v1/cryptocurrencies/<id>
curl http://localhost:8000/api/v1/cryptocurrencies/bitcoin/history?days=30
```

### 4. Manage watchlist
```bash
TOKEN=<your_access_token>
curl -X POST http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cryptocurrency_id": "<coin_uuid>"}'

curl http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer $TOKEN"
```

### 5. AI insight
```bash
curl http://localhost:8000/api/v1/cryptocurrencies/bitcoin/insight \
  -H "Authorization: Bearer $TOKEN"
```

## gRPC API

The AI insight endpoint is also available over gRPC on port `50051`.

Server reflection is enabled — use `grpcurl` without a `.proto` file:

```bash
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

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Postman Collection**: `postman/collection.json` (import into Postman with `postman/env.local.json`)

### Run Postman tests via Newman
```bash
npx newman run postman/collection.json -e postman/env.local.json
```

## Running Tests

```bash
# Requires local Postgres and Redis running
pytest tests/ -v --cov=app
```

## Deployment (AWS)

### Prerequisites
- AWS CLI configured
- Terraform >= 1.6
- Docker

### Steps

```bash
cd infra

# Initialize Terraform
terraform init

# Review plan
terraform plan -var="image_tag=latest" -var="db_password=yourpassword" \
  -var="secret_key=yoursecretkey" -var="internal_api_key=yourapikey" \
  -var="anthropic_api_key=yourkey"

# Apply (creates VPC, RDS, ElastiCache, ECS cluster, ALB)
terraform apply
```

The ALB DNS is output as `app_url`. Run migrations against the RDS instance before first request.

### CI/CD

The pipeline is structured in strict stages — no build runs until every security gate passes.

**Stage 1 — Security gates (parallel):**
| Job | Tool | What it catches |
|---|---|---|
| `pipeline-scan` | [poutine](https://github.com/boostsecurityio/poutine) | Injection in workflows, dangerous triggers, unpinned actions |
| `secret-scan` | [TruffleHog](https://github.com/trufflesecurity/trufflehog) | API keys / credentials in full git history |
| `sast` | [Semgrep](https://semgrep.dev) | OWASP Top 10, JWT misconfig, FastAPI-specific bugs |
| `sca` | pip-audit | CVEs in all dependencies (including transitive) |
| `lockfile-check` | pip-tools | `requirements.lock` out of sync with `requirements.txt` |
| `iac-validate` | Terraform + LocalStack | Infra config errors without touching real AWS |

**Stage 2 — Code quality (parallel, after Stage 1):**
- Ruff (lint), mypy (type check), pytest unit tests (no DB)

**Stage 3 — Integration tests:**
- pytest against real Postgres + Redis

**Stage 4 — E2E tests:**
- Newman runs the full Postman collection against a live server

**Stage 5 — Build & deploy (main branch only):**
- Docker image built, tagged with commit SHA, pushed to ECR
- ECS service updated (zero-downtime rolling deploy)

AWS credentials use **OIDC** — no long-lived secrets stored in GitHub. All Actions are pinned to immutable commit SHAs, never version tags.

Required GitHub Secrets: `AWS_OIDC_ROLE_ARN`, `AWS_REGION`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`

## Key Design Decisions

### Why PostgreSQL over MongoDB?
Crypto data is relational: users ↔ watchlists ↔ coins. Relational integrity, `ON CONFLICT DO UPDATE` upserts, and efficient range queries on price history make Postgres the right fit. For tick-level price storage at scale, TimescaleDB (a Postgres extension) would be the natural upgrade path.

### Why Redis?
Coin data changes once per minute at most. Without caching, every `GET /cryptocurrencies` hits the DB. Redis is shared across all container instances (unlike in-process dicts), and doubles as the rate-limit counter backend. AI insights are cached for 1 hour — Claude API calls are expensive and the analysis doesn't change per-minute.

### Why JWT + API Keys?
Not all endpoints are user-facing. `/refresh` is a privileged operation called by schedulers or internal services — it uses API key auth. User endpoints use short-lived JWTs (15 min) with refresh token rotation. In a real system, service-to-service auth would use AWS IAM + SigV4 or mTLS.

### Supply Chain Security
GitHub Actions are pinned to commit SHAs (not version tags, which can be moved). AWS credentials use OIDC — no static `AWS_ACCESS_KEY_ID` stored in GitHub Secrets. Docker images are tagged with git commit SHA, never `latest`.

The pipeline itself is scanned on every push by **poutine** — the same static analysis engine that powers [SmokedMeat](https://github.com/boostsecurityio/smokedmeat), a CI/CD red team framework used to find and exploit vulnerable workflows. Running poutine in CI means the pipeline validates its own defenses: if a future change introduces a dangerous trigger or an unpinned action, the build fails before any code runs.

To manually red-team the pipeline (requires Docker):
```bash
git clone https://github.com/boostsecurityio/smokedmeat.git
cd smokedmeat
make quickstart
# Enter your GitHub PAT and target this repo
# Expected result: no exploitable workflows found
```
