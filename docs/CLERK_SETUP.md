# Clerk setup (GeneGuidelines)

One Clerk application serves both `frontend-public` and `frontend-admin`.

Linked Clerk application: `app_3ED1xeHGOvOXgivNGCazHH68cIM`.

## CLI (local terminal)

The Clerk CLI needs an interactive terminal (it hangs in non-TTY environments).

```bash
clerk update --yes
clerk auth login
cd /path/to/GeneGuidelines
clerk init --app app_3ED1xeHGOvOXgivNGCazHH68cIM
clerk doctor
```

This repo is Vite + React (`@clerk/clerk-react`), not Next.js — no `middleware.ts` / `__clerk` proxy matcher. FastAPI verifies JWTs in `backend/clerk_auth.py`.

## Dashboard

1. Create an application at [clerk.com](https://clerk.com).
2. **Allowed origins** (Development + Production):
   - `http://localhost:5173` (public site)
   - `http://localhost:5174` (admin)
   - `https://geneguidelines.genequest.org` (production public)
   - Your admin host (e.g. `https://admin.geneguidelines.genequest.org`)
3. Copy **Publishable key** → `VITE_CLERK_PUBLISHABLE_KEY` (repo root `.env` for `make dev`, or each frontend `.env`).
4. Copy **Secret key** → `CLERK_SECRET_KEY` in the **same** env the API loads (repo root `.env` when using honcho; never in Vite).

**Both keys are required together.** If the public site signs users in with Clerk but the backend has no `CLERK_SECRET_KEY`, `/api/me` used to fall back to a local dev “admin” bypass and showed unlimited runs while Clerk still displayed `user`. With Clerk configured on the frontend, always set `CLERK_SECRET_KEY` on the backend and restart `make dev`.

## Roles (`publicMetadata`)

| Role | Research runs (24 h) | Admin panel (`:5174`) |
|------|----------------------|------------------------|
| `user` | 3 (bootstrap, guideline-run, pathway-run, official-guidelines-run) | No |
| `admin` | Unlimited | Yes |

Set on each user in Clerk Dashboard → User → Public metadata:

```json
{ "role": "user" }
```

```json
{ "role": "admin" }
```

- **Your account (first operator):** set `{"role":"admin"}` on your user after sign-up, then refresh the account page (or sign out/in). The API reads this from Clerk’s Users API when the session JWT does not include metadata yet.
- **Optional (faster, no extra API call):** Clerk Dashboard → **Configure** → **Sessions** → **Customize session token** → add:

  ```json
  {
    "role": "{{user.public_metadata.role}}"
  }
  ```

  The backend also checks `public_metadata` / `metadata` on the JWT when present.

- **New sign-ups:** Clerk Dashboard → **Configure** → **Sessions** → **Default user metadata**:

  ```json
  { "role": "user" }
  ```

- Quota status: `GET /api/me` (Bearer Clerk session JWT).

### macOS: `CERTIFICATE_VERIFY_FAILED` on `/api/me`

If the API returns 401 with SSL errors while fetching JWKS, Python on macOS may lack CA certs. The backend uses `certifi` for Clerk JWKS (see `requirements.txt`). After `pip install -r requirements.txt`, restart `make dev`.

Optional: run **Install Certificates.command** from your Python 3.x folder (Finder → Applications → Python), or set `SSL_CERT_FILE` to certifi’s bundle:

```bash
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
```

## Backend env

| Variable | Purpose |
|----------|---------|
| `CLERK_SECRET_KEY` | Derives issuer `https://<instance>` when `CLERK_ISSUER` unset |
| `CLERK_ISSUER` | Optional explicit JWT issuer |
| `CLERK_JWKS_URL` | Optional JWKS override |
| `CLERK_AUTHORIZED_PARTIES` | **Required in production** (or set `CLERK_REQUIRE_AUTHORIZED_PARTIES=1` to fail startup if missing). Comma-separated `azp` / audience values. When unset, any valid JWT from your Clerk instance is accepted. |
| `CLERK_REQUIRE_AUTHORIZED_PARTIES` | Set `1` to refuse startup without `CLERK_AUTHORIZED_PARTIES` |
| `ALLOW_DEV_AUTH_BYPASS` | Set `1` for local `make dev` without Clerk/API key (implicit admin). **Never in production.** |
| `CLERK_VERBOSE_AUTH_ERRORS` | Set `1` to include issuer/JWT details in 401 responses (debug only) |
| `CLERK_ROLE_CACHE_TTL_SEC` | Seconds to cache admin role from Clerk Users API (default `300`) |
| `METADATA_LOOKUP_RATE_LIMIT_MAX` | Per-user cap on `/lookup-disease-metadata` (default `30` / hour) |
| `METADATA_LOOKUP_RATE_LIMIT_WINDOW_SEC` | Window for metadata lookups (default `3600`) |
| `BOOTSTRAP_RATE_LIMIT_MAX_USER` | Default `3` / 24h |
| `BOOTSTRAP_RATE_LIMIT_WINDOW_SEC` | Default `86400` (24 h) |
| `BOOTSTRAP_RATE_LIMIT_MAX_PER_WINDOW` | Global cap across all users (default `50`) |
| `GENEGUIDELINES_API_KEY` | Break-glass for CI/scripts (maps to admin role) |

When neither Clerk nor API key is configured, local dev may use an implicit admin bypass only if `ALLOW_DEV_AUTH_BYPASS=1`.

## SSE (EventSource)

Browsers cannot send `Authorization` on EventSource. Pass the Clerk session JWT as:

- `?clerk_token=<session_jwt>`, or
- `?api_key=<GENEGUIDELINES_API_KEY>` (legacy)

**Security note:** Query-string tokens may appear in server access logs, browser history, and `Referer` headers. Clerk session JWTs are short-lived (~60 s), which limits exposure. Prefer header-based auth (`Authorization: Bearer`) for non-SSE requests. Where possible, use fetch-based streaming with headers instead of `EventSource`.

## Production checklist

1. Set `CLERK_SECRET_KEY` and matching `VITE_CLERK_PUBLISHABLE_KEY` on the same Clerk app.
2. Set `CLERK_AUTHORIZED_PARTIES` to your public and admin origins (see table above); use `CLERK_REQUIRE_AUTHORIZED_PARTIES=1` in deploy configs.
3. Keep `GENEGUIDELINES_API_KEY` unset on the public demo unless you need break-glass access.
4. Do **not** set `ALLOW_DEV_AUTH_BYPASS` in production.
5. Strip `clerk_token` from reverse-proxy access logs where possible.
