# ADR 001: Dual frontend apps and subdomain deploy

## Status

Accepted. Legacy `frontend/` and `design-reference/` removed during Kaggle publication cleanup.

## Context

GeneGuidelines splits into:

1. **Public site** — patients, families, and clinicians browsing living guidelines.
2. **Admin / operations** — workflow editing, pipeline runs, tool governance, PR review.

## Decision

- **`frontend-public`** and **`frontend-admin`** as separate Vite applications.
- Share UI primitives via **`packages/ui`** (`@gene-guidelines/ui`).
- Deploy target: **two subdomains** (e.g. `www` + `admin`), two build artefacts, one FastAPI backend.
- Root npm workspaces coordinate `dev:public` (port 5173) and `dev:admin` (port 5174).

## Consequences

- CI must lint/typecheck/build both apps and run backend pytest.
- CORS and API keys: public read-mostly; admin mutations protected.
- **Security:** the public app must **never** embed `VITE_GENEGUIDELINES_API_KEY` (or any secret) in its production bundle — Vite exposes all `VITE_*` values to the browser. Admin may use a shared ops key only with network controls; real user auth is a later phase.
- Shared design tokens live in `packages/ui` to avoid visual drift.
- Deploy artefacts are only `frontend-public/dist` and `frontend-admin/dist`.

## Alternatives considered

- Single app with `/admin` routes — rejected to keep bundle size and security boundaries clear for subdomain deploy.
