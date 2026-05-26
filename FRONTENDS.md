# Frontends

| App | Directory | Dev port | Purpose |
|-----|-----------|----------|---------|
| Public | `frontend-public/` | 5173 | Patient/clinician site |
| Admin | `frontend-admin/` | 5174 | Operations panel |

## Commands (from repo root)

```bash
npm install

npm run dev:public    # http://localhost:5173
npm run dev:admin     # http://localhost:5174  — both apps can run in parallel

# Production-like local preview (proxies /api → :8000 — start uvicorn first)
npm run preview -w frontend-public   # http://localhost:4173
npm run preview -w frontend-admin    # http://localhost:4174

npm run lint
npm run typecheck
npm run build:frontends
```

Backend (unchanged):

```bash
python -m uvicorn backend.main:app --reload
```

## API base URL

Leave `VITE_API_URL` unset during `vite dev` / `vite preview` so requests use relative `/api/...` and the Vite proxy forwards to `http://127.0.0.1:8000`.

For static hosting without a dev server proxy, build with `VITE_API_URL=https://your-api.example.com` (origin only, **no** `/api` suffix — paths already include `/api/...`).

## Shared UI

`packages/ui` — `@gene-guidelines/ui` (tokens, `AppHeader`, shared primitives). `packages/ops` — `@gene-guidelines/ops` (admin widgets used by `frontend-admin`: flow canvas, node editor, run trace, governance panels).

## Clerk authentication

Setup: [`docs/CLERK_SETUP.md`](docs/CLERK_SETUP.md).

| App | Env (client) | Env (server) |
|-----|----------------|--------------|
| Public | `VITE_CLERK_PUBLISHABLE_KEY` | `CLERK_SECRET_KEY` (+ optional `CLERK_AUTHORIZED_PARTIES`) |
| Admin | same publishable key | same secret |

Roles live in Clerk **public metadata**: `{"role":"user"}` or `{"role":"admin"}`.

- **Public catalog** (`GET /api/diseases`, …) stays open without login.
- **Research / bootstrap** requires a signed-in user (`user` role).
- **Admin panel** requires `admin` role (Clerk) or break-glass `GENEGUIDELINES_API_KEY` (CI/scripts).

SSE trace URLs pass `?clerk_token=` (or legacy `?api_key=`) because EventSource cannot send headers.

## Security (deploy)

- **Public:** never set `VITE_GENEGUIDELINES_API_KEY` in the production bundle. Use Clerk session JWTs for `POST /api/pipeline/*` and run polling.
- **Admin:** set `VITE_CLERK_PUBLISHABLE_KEY` on both frontends; set `CLERK_SECRET_KEY` on the API. Optionally keep `GENEGUIDELINES_API_KEY` for automation only (not in browser builds).
- Deploy admin on a restricted hostname; edge basic-auth is optional extra cover now that Clerk gates the React shell.
- Only ship `dist/` outputs from `frontend-public` and `frontend-admin` to your CDN.
