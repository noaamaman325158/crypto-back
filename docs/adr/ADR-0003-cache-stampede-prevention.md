# ADR-0003: Cache stampede prevention with a Redis lock

**Status:** Accepted
**Date:** 2026-06-21
**Deciders:** Backend
**Implements:** `app/core/cache.py` (`cache_get_or_set`)

## Context

Read endpoints are Redis-cached with short TTLs (60s on coin data). When a hot
key expires under concurrent load, every in-flight request misses simultaneously
and all of them recompute the value — a "thundering herd" / cache stampede — which
amplifies a single miss into N simultaneous DB queries (or upstream calls).

## Decision

Implement `cache_get_or_set()` with a Redis distributed lock (`SET NX PX`). On a
miss, exactly one caller acquires `lock:<key>` and runs the factory; all other
concurrent callers poll briefly and then read the value the winner populated. The
lock has a `lock_timeout`; if the holder dies, waiters fall back to computing the
value themselves so a request never hangs indefinitely.

## Options Considered

### Option A: Redis `SET NX` lock (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — lock acquisition, double-check, timeout fallback |
| Cost | Low — one extra Redis op on miss |
| Scalability | High — works across all app instances (shared Redis) |
| Team familiarity | Medium |

**Pros:** factory runs once per miss across the whole fleet; cross-instance;
bounded fallback so no indefinite waits.
**Cons:** more moving parts; the timeout fallback can still let >1 caller compute
in the rare case the lock holder stalls.

### Option B: No lock (plain cache-aside)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Lowest |
| Cost | High under load — N concurrent recomputes per miss |
| Scalability | Poor on hot keys |
| Team familiarity | High |

**Pros:** trivial.
**Cons:** thundering herd on every hot-key expiry.

### Option C: In-process lock (e.g. `asyncio.Lock` per key)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Low |
| Scalability | Poor — only dedupes within one process |
| Team familiarity | High |

**Pros:** no Redis round-trip.
**Cons:** with multiple ECS tasks, each instance still recomputes once — herd is
reduced, not eliminated.

## Trade-off Analysis

Option C only helps within a single process; with multiple app instances the herd
returns at instance granularity. Option A is the only one that dedupes across the
fleet, which matters because the service runs multiple ECS tasks behind an ALB.
The added complexity is contained in one well-tested helper.

## Consequences

- **Easier:** hot-key expiry no longer spikes DB/upstream load.
- **Harder:** the helper has subtle edge cases (lock-holder death, double-check
  after acquiring) that must be preserved on changes.
- **Revisit if:** we adopt a cache library with built-in single-flight, or move to
  request coalescing at a different layer.

## Known follow-ups

- The timeout fallback path computes without re-acquiring the lock — acceptable as
  a safety valve, but it weakens the guarantee in the rare stall case.

## Action Items

1. [x] `cache_get_or_set()` with `SET NX PX` lock + double-check.
2. [x] Bounded poll-and-fallback so requests never hang.
3. [ ] Consider re-acquire-on-fallback to tighten the single-flight guarantee.
