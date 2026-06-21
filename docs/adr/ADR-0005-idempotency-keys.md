# ADR-0005: Idempotency keys for mutating endpoints

**Status:** Accepted
**Date:** 2026-06-21
**Deciders:** Backend
**Implements:** `app/core/idempotency.py`, used by
`POST /cryptocurrencies/refresh` and `POST /watchlist`

## Context

Mutating POST endpoints are not naturally safe to retry. A client that times out
and retries `POST /refresh` could trigger duplicate CoinGecko refreshes; a retry of
`POST /watchlist` could create duplicate entries (or surface a confusing 409). Network
flakiness makes retries common, so we need retries to be safe.

## Decision

Support an optional `Idempotency-Key: <uuid>` header on mutating endpoints. The key
is stored in Redis with a TTL. If a request arrives with a key we have already seen
inside the window, we return the stored result without re-executing the operation.
TTLs are tuned per endpoint: **30s on `/refresh`** (short — just absorbs immediate
retries of an async trigger) and **24h on `/watchlist`** (long — a watchlist add
should not be duplicated even on a much later retry).

## Options Considered

### Option A: Redis idempotency keys (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — small helper, Redis we already run |
| Cost | Low — one Redis read + write per mutating call |
| Scalability | High — shared Redis works across instances |
| Team familiarity | High |

**Pros:** safe retries across the fleet; reuses existing Redis; per-endpoint TTL.
**Cons:** the stored value must be JSON-serializable and round-trip cleanly back
into the response schema.

### Option B: Database unique constraints only
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low for some cases |
| Cost | Low |
| Scalability | High |
| Team familiarity | High |

**Pros:** strong guarantee for entity-creating endpoints (e.g. unique
(user, coin) on watchlist).
**Cons:** doesn't cover non-DB side effects like `/refresh` triggering CoinGecko;
turns a duplicate into a 409 rather than a transparent replay.

### Option C: Nothing — clients must dedupe
**Pros:** no server work.
**Cons:** pushes correctness onto every client; duplicates leak through.

## Trade-off Analysis

DB constraints (Option B) are a good *complement* for the watchlist (and are in
fact enforced), but they don't help `/refresh`, whose side effect is an external
call, not a row. Option A is the general mechanism that covers both, with a single
small helper and TTLs tuned to the semantics of each endpoint.

## Consequences

- **Easier:** clients can safely retry POSTs; no duplicate refreshes or watchlist
  rows from network retries.
- **Harder:** stored responses must serialize cleanly (serialize via the response
  schema, never raw ORM `__dict__`); TTL choice is a semantic decision per endpoint.
- **Revisit if:** we add mutating endpoints with large/streaming responses where
  caching the full response in Redis is impractical.

## Action Items

1. [x] `Idempotency-Key` header + Redis store/check helper.
2. [x] 30s TTL on `/refresh`, 24h on `/watchlist`.
3. [x] Serialize stored values through the response schema (not ORM internals).
