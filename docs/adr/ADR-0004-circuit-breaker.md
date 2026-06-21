# ADR-0004: In-process circuit breaker for external dependencies

**Status:** Accepted
**Date:** 2026-06-21
**Deciders:** Backend
**Implements:** `app/core/circuit_breaker.py`, used by `app/providers/coingecko.py`
and `app/services/ai_insight_service.py`

## Context

The system depends on two external APIs: CoinGecko (via the worker) and Anthropic
Claude (for AI insights). When an upstream is failing, continuing to send requests
wastes time on calls that will fail, ties up connections, and slows the whole
service. We want to fail fast during an outage and probe for recovery, without a
heavyweight resilience framework.

## Decision

Implement a lightweight in-process `CircuitBreaker` async context manager with the
standard three states:

- **CLOSED** — requests pass through; consecutive failures increment a counter.
- **OPEN** — after `failure_threshold` failures, reject immediately with `503` for
  `recovery_timeout` seconds (no network I/O).
- **HALF_OPEN** — after the timeout, allow one probe; success closes, failure
  re-opens.

One breaker per dependency: CoinGecko (5 failures / 30s recovery), Claude
(3 failures / 60s recovery). State is exported as a Prometheus gauge. A
client-side condition like a 404 (`NotFoundError`) is configured via
`ignored_exceptions` and does **not** count as a failure — only infrastructure
errors (5xx, network, timeout) move the breaker.

## Options Considered

### Option A: In-process custom breaker (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — ~100 lines, no dependency |
| Cost | None |
| Scalability | Per-instance state (acceptable) |
| Team familiarity | High — readable, fully owned |

**Pros:** no extra dependency; tailored exception handling (`ignored_exceptions`);
easy to test and reason about.
**Cons:** state is per-process, not shared across instances; we own the correctness.

### Option B: Library (e.g. pybreaker / aiobreaker)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Extra dependency |
| Scalability | Per-instance too |
| Team familiarity | Medium |

**Pros:** battle-tested.
**Cons:** another dependency to audit (supply chain); less control over the
"don't count 4xx" behavior we specifically need.

### Option C: Rely on timeouts + retries only
**Pros:** simplest.
**Cons:** no fast-fail — every request still pays the timeout during an outage;
no recovery probing.

## Trade-off Analysis

Per-instance state (Option A and B) means each ECS task learns of an outage
independently — acceptable, since an upstream outage affects all instances quickly
anyway, and a shared/distributed breaker adds Redis coupling for little gain. The
decisive factor for A over B is the need to **exclude client-side 4xx from the
failure count** (a 404 for an unknown coin must not trip the breaker), which is
cleanest with code we own.

## Consequences

- **Easier:** during an upstream outage, requests fail fast instead of hanging;
  recovery is probed automatically; breaker state is observable in Prometheus.
- **Harder:** breaker state lives per-process; correctness of the state machine is
  on us (covered by unit tests).
- **Revisit if:** we need fleet-wide breaker coordination, or adopt a service mesh
  that provides this at the network layer.

## Action Items

1. [x] Three-state breaker as an async context manager.
2. [x] Per-dependency thresholds (CoinGecko 5/30s, Claude 3/60s).
3. [x] `ignored_exceptions` so 404s don't trip the breaker.
4. [x] Prometheus gauge for breaker state.
