# ADR 003 — Auth0 (EU) as identity provider; roles in our database

## Status
Accepted

## Context

D1 ("accounts and verification") needs authenticated users: parents, doctors,
researchers, and operators (superadmins). The earlier exploration used Clerk
(PR #13, branch `feat/clerk-auth-integration`); that branch is kept only as a
structural reference and is not merged.

The product is built by a Polish non-profit handling health-adjacent data, so
the identity provider must offer an **EU data region**. We must also be able to
merge auth scaffolding incrementally without breaking the existing API-key gate
that scripts, CI, and the admin panel rely on today.

FastAPI's idiomatic authorization mechanism is the dependency system
(`Depends`), not middleware: it is per-route, typed, composable, and — crucially
for tests — overridable via `app.dependency_overrides`, which middleware cannot
match.

## Decision

1. **Auth0, EU tenant (Frankfurt), is the identity provider only.** It issues
   and signs RS256 access tokens. The backend verifies them with
   `PyJWT[crypto]` + `PyJWKClient` (built-in JWKS caching) — no hand-rolled
   crypto, no `python-jose`, no manual JWKS fetch. We check signature, `iss`
   (`https://{AUTH0_DOMAIN}/`), `aud` (`AUTH0_AUDIENCE`), and `exp` (small
   leeway).

2. **Roles, verification, ORCID, and institution live in our `users` table,
   not in IdP metadata.** Authorization decisions (ranking weights in D5, gating
   in D7) are queries against our database; keeping the state local avoids stale
   tokens after a role change and keeps the IdP swappable (the Clerk → Auth0
   move confirmed the value of that portability). Auth0 owns identity; we own
   authorization.

3. **Just-in-time provisioning.** The first request bearing a valid JWT inserts
   a `users` row keyed by the Auth0 `sub`. No separate "register in backend"
   step.

4. **Superadmin bootstrap via environment.** `SUPERADMIN_EMAILS` (CSV) grants
   the `superadmin` role on login when the JWT marks the email verified. It is
   re-evaluated on every login, so adding an address promotes that user on their
   next request. No manual SQL.

5. **Role is a one-time self-selection.** `users.role` starts `NULL`; the
   frontend forces a parent/doctor/researcher choice. Changing it afterward
   requires a superadmin. `doctor` leaves `verified = false` pending approval.

6. **The API key is retained as a machine credential.** `require_superadmin`
   passes when **either** a valid `GENEGUIDELINES_API_KEY` is presented (reusing
   the single timing-safe comparison in `backend/auth.py`) **or** a valid JWT
   maps to a superadmin user. This makes the rollout fail-safe: merging before
   the Auth0 tenant exists breaks nothing, and CI/scripts keep working.

7. **Fail-closed, but the app boots without Auth0.** When `AUTH0_DOMAIN` is
   unset the verifier is disabled: public endpoints keep working, and
   JWT-protected dependencies return `503 "Auth0 not configured"` rather than
   silently accepting anything.

8. **Guards are `Depends`-based, not middleware.** `CurrentUser` /
   `OptionalUser` annotations, a `require_role(*roles)` factory (superadmin
   always passes), `require_superadmin`, and `require_verified_doctor` (for D5).

## Consequences

- New domain `backend/account/` mirrors `backend/content/`
  (models / contracts / repository / service / deps / api / jwt), SQLAlchemy 2.0
  Core (not ORM) on the shared persistence layer.
- A `users` table is added via Alembic with generic column types so the same
  migration applies on both SQLite (offline alembic / Kaggle snapshot) and
  Postgres (production engine).
- AUTH-2 enforces these guards across the admin endpoints; AUTH-3 wires the two
  frontends; AUTH-4 adds doctor invites and ORCID verification. None of those
  require re-touching the verification core.
- ORCID is treated as app-level verification (a future env-gated OAuth), never
  as a login mechanism, so it does not bind the IdP choice.

Manual tenant setup (region, API audience, SPA callback origins, the non-profit
50% application) is documented in the D1 plan and does not block code.
