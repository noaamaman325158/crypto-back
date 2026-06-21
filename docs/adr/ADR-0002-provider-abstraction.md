# ADR-0002: Provider abstraction (`CryptoProvider` ABC)

**Status:** Accepted
**Date:** 2026-06-21
**Deciders:** Backend
**Implements:** `app/providers/base.py`, `app/providers/coingecko.py`

## Context

CoinGecko is the current market-data source, but it is not the only option
(CoinMarketCap, Coinpaprika, a paid feed). Vendor lock-in is a risk: pricing,
rate limits, and terms can change. We also want cross-cutting concerns —
circuit breaking, metrics, error mapping — applied uniformly regardless of vendor.

## Decision

Define an abstract base class `CryptoProvider` (`app/providers/base.py`) with the
data-source contract (`fetch_markets`, `fetch_history`). `CoinGeckoProvider`
implements it. All service and worker code depends on the abstraction, never on
`CoinGeckoProvider` directly. A single factory, `get_crypto_provider()`, selects
the active implementation. The circuit breaker and Prometheus metrics are attached
**at the provider layer**, so any new provider inherits them automatically.

## Options Considered

### Option A: ABC + factory (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low — one ABC, one factory function |
| Cost | None |
| Scalability | N/A |
| Team familiarity | High — standard dependency-inversion pattern |

**Pros:** swap vendors by changing one function; cross-cutting concerns live in
one place; services are testable with a fake provider.
**Cons:** slight indirection; the ABC must stay generic enough across vendors.

### Option B: Call CoinGecko client directly from services
| Dimension | Assessment |
|-----------|------------|
| Complexity | Lowest |
| Cost | High later — vendor swap touches every call site |
| Scalability | N/A |
| Team familiarity | High |

**Pros:** least code now.
**Cons:** vendor lock-in; circuit breaker/metrics duplicated at each call site;
hard to unit-test services without network mocks.

## Trade-off Analysis

The indirection cost of Option A is trivial (one ABC, one factory). The payoff —
single swap point, centralized resilience/observability, and trivially mockable
services — is large and compounds over time. Option B trades a tiny short-term
saving for scattered, duplicated cross-cutting logic.

## Consequences

- **Easier:** changing data source; unit-testing services with a fake provider;
  consistent metrics/circuit-breaking.
- **Harder:** the ABC contract must accommodate differences between vendor APIs
  (field names, pagination, history shape).
- **Revisit if:** a second provider's API diverges so much that the shared
  contract leaks vendor-specific assumptions.

## Action Items

1. [x] `CryptoProvider` ABC defines the contract (`base.py`).
2. [x] `get_crypto_provider()` is the single selection point.
3. [x] Circuit breaker + metrics attached at the provider layer.
4. [ ] Add a second provider implementation to validate the abstraction holds.
