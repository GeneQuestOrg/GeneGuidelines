# ADR 002 — Doctor Map feature split into stacked PRs

## Status
Proposed

## Context

The original PR #16 ("Doctor Map and Authentication Integration") was a 122-file, ~1 000-line diff targeting `production` directly. It mixed the doctor-map feature with auth/account changes that overlap with PR #13. The PR could not be safely reviewed or merged.

Per the project's PR guidelines (≤ 500 lines, one feature per PR, base on `main` not `production`), the diff was split.

## Decision

Extract only the doctor-map feature into **4 stacked PRs**, each based on the previous. Auth/account/rate-limit work stays in PR #13.

### Merge order

```
main ← #13 (super_admin + model profile override)
         └── A: feat/doctor-map-backend        (~205 lines)
               └── B: feat/doctor-map-components  (~325 lines)
                     └── C1: feat/doctor-map-wiring   (~384 lines)
                               └── C2: feat/doctor-map-e2e  (~110 lines)
```

### PR A — Backend geo endpoint (`feat/doctor-map-backend`)

| File | Purpose |
|---|---|
| `backend/routers/geo.py` | `/api/geo/search` — Nominatim proxy, per-IP rate limit, env-var contact |
| `backend/main.py` | Register geo router; fix `Permissions-Policy: geolocation=(self)` |
| `backend/doctor_catalog.py` | Fix `catalog_slugs` init order |
| `backend/tests/test_geo_router.py` | 6 unit tests |
| `.github/workflows/ci.yml` | Add postgres service for CI |

Independently testable via `curl /api/geo/search?q=Warsaw` before any frontend lands.

### PR B — Frontend components (`feat/doctor-map-components`)

| File | Purpose |
|---|---|
| `frontend-public/src/components/DoctorsMap.tsx` | Leaflet map, MarkerCluster, role-colored pins |
| `frontend-public/src/components/LocationPicker.tsx` | Search input with AbortController, GPS button |
| `frontend-public/src/components/DoctorCard.tsx` | Distance pill, validated role CSS class |
| `frontend-public/src/api/geo.ts` | Typed API client for `/api/geo/search` |
| `frontend-public/src/utils/doctorLabels.ts` | `VALID_PUBMED_ROLES` export, label alignment |

Components exist but are not yet rendered anywhere — feature is invisible to users until C1.

### PR C1 — Wiring and styles (`feat/doctor-map-wiring`)

| File | Purpose |
|---|---|
| `frontend-public/src/views/DoctorsView.tsx` | Integrates LocationPicker, distance filter chips, view-mode toggle |
| `frontend-public/src/styles/doctors.css` | Map layout, picker, chips, toggle, responsive breakpoints |

This is the PR that makes the feature visible to users.

### PR C2 — E2E tests (`feat/doctor-map-e2e`)

| File | Purpose |
|---|---|
| `frontend-public/e2e/doctors-geolocation.spec.ts` | GPS grant/deny, map pins, location search, distance filter |

Added after C1 so tests run against a fully wired feature.

## Consequences

- Each PR is independently reviewable and under 500 lines.
- Stacking means GitHub automatically retargets each PR to `main` as its predecessor merges.
- The old `feat/doctor-map` branch (single large commit) is superseded by these four and can be deleted after all four merge.
- Auth/account/rate-limit code from the original PR #16 is intentionally excluded — it belongs in PR #13 or a follow-up.
