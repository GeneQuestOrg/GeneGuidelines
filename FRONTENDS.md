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

## Prerendered FD pages

`npm run build:public` runs `node prerender/build.mjs` after `vite build`. It writes a static copy of the four fibrous-dysplasia pages — `/diseases/fd`, `/diseases/fd/map`, `/diseases/fd/tests`, `/diseases/fd/guidelines`, each in both languages — to `dist/<path>/index.html`, with that page's title, description, Open Graph tags and JSON-LD, and a readable body inside `#gg-prerender`. Before this, `/pl/diseases/fd` returned 68 characters: a crawler, a link preview and a language model saw a title and nothing else.

The content comes from the locale catalogues that are checked in, because the build runs in CI with no backend and no database. Anything that lives only in the database — the AI synthesis, the doctor list, the trial list — is named and linked, never invented at build time. `main.tsx` removes `#gg-prerender` before React mounts, and `spa_fallback` in `backend/main.py` serves `<path>/index.html` for a directory path, which is what makes the files reachable at all.

## API base URL

Leave `VITE_API_URL` unset during `vite dev` / `vite preview` so requests use relative `/api/...` and the Vite proxy forwards to `http://127.0.0.1:8000`.

For static hosting without a dev server proxy, build with `VITE_API_URL=https://your-api.example.com` (origin only, **no** `/api` suffix — paths already include `/api/...`).

## Shared UI

`packages/ui` — `@gene-guidelines/ui` (tokens, `AppHeader`, shared primitives). `packages/ops` — `@gene-guidelines/ops` (admin widgets used by `frontend-admin`: flow canvas, node editor, run trace, governance panels).

## Security (deploy)

- **Public:** never set `VITE_GENEGUIDELINES_API_KEY` in the production build — Vite exposes every `VITE_*` value in the JS bundle. The public app should call the backend over open routes only.
- **Admin must not be on a public URL** until real user auth ships. For deploy:
  1. Set `GENEGUIDELINES_API_KEY` in the backend `.env` to enable the API-key check in `backend/auth.py`.
  2. Deploy the admin build to a non-guessable hostname (e.g. `admin-<random>.geneguidelines.example`) and **do not link it from the public site**.
  3. Add a basic-auth or IP-allowlist gate at the edge (Cloudflare Access, Render password protect, nginx auth_basic) for double cover.
  4. The admin app must be built with `VITE_GENEGUIDELINES_API_KEY` so SSE traces and protected endpoints work; this is acceptable only because the admin URL itself is gated.
- Only ship `dist/` outputs from `frontend-public` and `frontend-admin` to your CDN. Nothing else from the repo.
