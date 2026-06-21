# Architecture Decision Records

This directory records the significant architectural decisions for the Crypto
Dashboard API. Each ADR captures the context, the decision, the options
considered, the trade-offs, and the consequences of one decision.

These records are **retrospective** — they document decisions already made and
implemented in the codebase (see the "Key Design Decisions" section of the root
`README.md` for the condensed version).

| ADR | Title | Status |
|-----|-------|--------|
| [0001](ADR-0001-push-based-data-pipeline.md) | Push-based data pipeline (no provider calls at request time) | Accepted |
| [0002](ADR-0002-provider-abstraction.md) | Provider abstraction (`CryptoProvider` ABC) | Accepted |
| [0003](ADR-0003-cache-stampede-prevention.md) | Cache stampede prevention with a Redis lock | Accepted |
| [0004](ADR-0004-circuit-breaker.md) | In-process circuit breaker for external dependencies | Accepted |
| [0005](ADR-0005-idempotency-keys.md) | Idempotency keys for mutating endpoints | Accepted |
| [0006](ADR-0006-auth-jwt-and-api-keys.md) | Authentication — JWT for users, API keys for services | Accepted |

## Format

Each ADR follows: **Context → Decision → Options Considered → Trade-off Analysis
→ Consequences → Action Items**. Status is one of `Proposed`, `Accepted`,
`Deprecated`, `Superseded`.

## Adding a new ADR

1. Copy the structure of an existing ADR.
2. Use the next sequential number (`ADR-0007-...`).
3. Add a row to the table above.
4. Start at `Proposed`; move to `Accepted` once the decision is made.
