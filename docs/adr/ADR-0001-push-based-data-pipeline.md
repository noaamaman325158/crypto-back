# ADR-0001: Push-based data pipeline (no provider calls at request time)

**Status:** Accepted
**Date:** 2026-06-21
**Deciders:** Backend
**Implements:** `app/worker/refresh_job.py`, `app/services/crypto_service.py`, `app/api/v1/endpoints/`

## Context

The dashboard serves cryptocurrency market data sourced from CoinGecko. CoinGecko
has its own rate limits, latency, and availability SLA. If every user-facing read
called CoinGecko directly:

- CoinGecko's latency and outages would be inside our own latency/error budget.
- Concurrent reads would multiply into many upstream calls, hitting rate limits fast.
- A CoinGecko outage would take down our read path entirely.

We need read endpoints that are fast, predictable, and resilient to upstream
problems, for a bounded universe of coins (top ~500 by market cap).

## Decision

Adopt a **push-based pipeline**. A separate scheduled worker
(`app/worker/refresh_job.py`) is the *only* component that calls CoinGecko, every
5 minutes. It writes to PostgreSQL (system of record) and write-through populates
Redis. User-facing APIs read **PostgreSQL → Redis only** and never call CoinGecko
at request time. The one exception is the privileged `POST /refresh` escape hatch
(service-to-service, `X-API-Key`), which triggers an on-demand fetch in the
background.

Every coin response includes `data_age_seconds` so clients know exactly how fresh
the data is.

## Options Considered

### Option A: Push pipeline (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — extra worker process, scheduling, locking |
| Cost | Low — bounded, predictable CoinGecko call volume |
| Scalability | High — reads scale with our DB/cache, not CoinGecko |
| Team familiarity | High — standard worker + cache pattern |

**Pros:** CoinGecko removed from request latency; survives upstream outages;
predictable upstream load; cache stampede is bounded.
**Cons:** Data is up to N minutes stale; needs a worker process and worker
liveness monitoring (`RefreshWorkerDown` alert).

### Option B: Pull / cache-aside at request time
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — no worker |
| Cost | High — call volume tracks traffic, hits rate limits |
| Scalability | Low — coupled to CoinGecko SLA |
| Team familiarity | High |

**Pros:** Simpler, no second process; data is as fresh as the last cache miss.
**Cons:** CoinGecko outage = our outage; thundering herd on cold cache; rate-limit
risk under load.

## Trade-off Analysis

The core trade-off is **freshness vs. resilience**. Option B gives marginally
fresher data but couples our availability and latency to a third party we don't
control. For a market dashboard, data that is a few minutes old is acceptable;
an outage is not. Option A makes the staleness explicit and measurable
(`data_age_seconds` + `CoinDataStale` alert) instead of hiding it.

## Consequences

- **Easier:** read endpoints are fast and stay up during CoinGecko outages;
  upstream cost is predictable.
- **Harder:** we now run and must monitor a worker; data is intentionally stale.
- **Revisit if:** we need sub-minute freshness, or the coin universe grows large
  enough that a full refresh every 5 minutes is too expensive.

## Action Items

1. [x] Scheduled worker owns all CoinGecko traffic (`refresh_job.py`).
2. [x] `data_age_seconds` in every coin response.
3. [x] `CoinDataStale` / `RefreshWorkerDown` alerts.
4. [ ] Document expected staleness SLO for clients.
