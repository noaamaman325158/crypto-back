# ADR-0006: Authentication — JWT for users, API keys for services

**Status:** Accepted
**Date:** 2026-06-21
**Deciders:** Backend
**Implements:** `app/core/security.py`, `app/api/v1/dependencies.py`,
`app/services/auth_service.py`

## Context

The API has two distinct classes of caller with different needs:

1. **End users** (browser/app) — log in, browse, manage a watchlist, request AI
   insights. They need short-lived, stateless credentials and a way to stay logged
   in without re-entering a password.
2. **Internal services** — call the privileged `POST /refresh`. They need a simple,
   long-lived, non-interactive credential.

We also had a supply-chain constraint: `python-jose` pins `pyasn1<0.5.0`, which
conflicts with the CVE fix `pyasn1>=0.6.3`.

## Decision

- **Users:** JWT access tokens (15 min) + refresh tokens (7 days), signed with
  `HS256` using **PyJWT** (not python-jose). Refresh tokens are rotated on use and
  the current one is stored on the user row so it can be revoked. Passwords hashed
  with bcrypt. RBAC via a `role` claim (`user` / `admin`).
- **Services:** a static `INTERNAL_API_KEY` passed as `X-API-Key`, validated with a
  constant-time comparison (`hmac.compare_digest`).

## Options Considered

### Token library: PyJWT (chosen) vs python-jose
| Dimension | PyJWT | python-jose |
|-----------|-------|-------------|
| Maintenance | Active | Less active |
| Dependencies | None problematic | Pins `pyasn1<0.5.0` (CVE conflict) |
| Features | JWT (sufficient) | JWE/JWK extras (unused) |

**Decision:** PyJWT — the unused extras of python-jose aren't worth a transitive
CVE conflict.

### User auth: JWT access + refresh (chosen) vs server-side sessions
**Pros (JWT):** stateless, no session store on the read path, scales horizontally.
**Cons (JWT):** access tokens can't be revoked before expiry — mitigated by a short
15-min lifetime plus server-stored, rotatable refresh tokens.

### Service auth: static API key (chosen) vs mTLS / OAuth client-credentials
**Pros (API key):** trivial for internal service-to-service; constant-time compare
avoids timing leaks.
**Cons (API key):** long-lived shared secret — acceptable for one internal caller,
stored in SSM Parameter Store, never in code.

## Trade-off Analysis

The two caller classes have genuinely different requirements, so a single scheme
would compromise one of them. JWT fits stateless user traffic; a static key fits a
non-interactive internal caller. The short access-token lifetime + rotatable
refresh token gives most of the revocation benefit of sessions without a
session store on the hot path. PyJWT over python-jose is driven by supply-chain
hygiene, not features.

## Consequences

- **Easier:** stateless horizontal scaling; clean separation of user vs service
  auth; revoke a user by clearing their stored refresh token.
- **Harder:** access tokens are valid until expiry (no instant revoke); the
  internal API key is a shared secret that must be rotated operationally.
- **Revisit if:** we need instant access-token revocation (add a deny-list /
  introduce token versioning), or more than one internal service with distinct
  identities (move to client-credentials / mTLS).

## Action Items

1. [x] PyJWT-based access (15m) + refresh (7d) tokens.
2. [x] Refresh-token rotation + server-side storage for revocation.
3. [x] bcrypt password hashing; RBAC `role` claim.
4. [x] `X-API-Key` with constant-time comparison for service auth.
5. [ ] Decide on an instant-revocation strategy for access tokens if required.
