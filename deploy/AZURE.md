# Azure deployment (GeneGuidelines)

**GeneGuidelines** is an open-source project maintained by the [**GeneQuest Foundation**](https://genequest.org) — living clinical guidelines for rare genetic diseases, built on a controlled AI workflow over PubMed evidence. The codebase is published under **CC-BY 4.0**; see the [project README](../README.md) for scope and motivation.

This document describes how the **GeneQuest-hosted instance** at [geneguidelines.genequest.org](https://geneguidelines.genequest.org) is deployed on **Azure Container Apps**. Custom domain and TLS are configured in the Azure portal (not in this repo).

Contributors who fork the project can reuse these patterns on their own Azure subscription; resource names below refer to the foundation’s deployment.

## Live site

| Item | Value |
|---|---|
| **URL** | https://geneguidelines.genequest.org |
| **Health** | `GET /health` → `{"status":"ok"}` |
| **API** | Same host — SPA and `/api/*` served from one container |

## Azure resources

These names are required for deploy scripts and GitHub Actions. They are not secrets; scope your service principal to the resource group only.

| Resource | Name |
|---|---|
| Resource group | `geneguidelines-demo` |
| Container App | `gg-public` |
| Azure Container Registry | `ggdemo45223` |
| Image | `ggdemo45223.azurecr.io/geneguidelines-backend:<tag>` |

> Resource group and registry names retain a `-demo` suffix from early hosting; the instance serves the public GeneGuidelines product, not a throwaway prototype.

To inspect the currently running revision and image:

```bash
az containerapp show \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --query "properties.{revision:latestRevisionName,image:template.containers[0].image}" \
  -o json
```

## Docker image

Build from repo root using **`Dockerfile.backend`**.

- **Backend**: FastAPI + Uvicorn on port **8000**, single worker (SSE / in-process state).
- **Public frontend**: `frontend-public/dist` copied to **`/app/static`** — FastAPI serves SPA + API (CSP in `backend/main.py`).
- **Database**: Postgres via `DB_URL` (see `backend/.env.example`). Local Compose uses the `postgres-data` volume.
- **Seed**: on an empty database, loads `backend/content_*_seed.json` (diseases, trials, therapies, foundations).

Before building to ACR (Auth0 values are public — they ship in the client bundle):

```bash
VITE_API_URL="" \
VITE_AUTH0_DOMAIN=genequest.eu.auth0.com \
VITE_AUTH0_CLIENT_ID=eIjwuYWNv6ygMR0Ib1Z9T891qC2q9aXI \
VITE_AUTH0_AUDIENCE=https://api.geneguidelines.genequest.org \
  npm run build:public
az acr build --registry ggdemo45223 \
  --image geneguidelines-backend:vNEXT \
  --file Dockerfile.backend .
```

Unset `VITE_API_URL` (or set it to `""`) so the SPA calls same-origin `/api/*` on the Container App host.

## Source branch

| Item | Value |
|---|---|
| Deploy branch | **`production`** (push → GitHub Actions → Azure) |

Features merged to `production` are deployed to the hosted instance automatically. Work on other branches stays local until merged.

## LLM configuration (SiliconFlow)

The backend runs in **vLLM-compatible** mode (`MODEL_PROFILE=vllm` + `LLM_BASE_URL` + `LLM_API_KEY` → `SINGLE_LLM_MODE` in `backend/config.py`). The hosted instance uses **SiliconFlow** as the primary LLM provider.

| Container App env var | Hosted value |
|---|---|
| `MODEL_PROFILE` | `vllm` |
| `LLM_BASE_URL` | `https://api.siliconflow.com/v1` |
| `LLM_MODEL` | `google/gemma-4-31B-it` |
| `LLM_API_KEY` | `secretref:llm-api-key` |
| `DB_URL` | Azure PostgreSQL connection string (`secretref:db-url` or env) |
| `LLM_AUTH_HEADER_STYLE` | `bearer` |
| `OPENAI_API_KEY` | placeholder (API compatibility; unused in vLLM mode) |
| `OPENROUTER_API_KEY` | `secretref:openrouter-key` |

### Container App secrets (names only — values live in Azure)

| Secret name | Purpose |
|---|---|
| `llm-api-key` | SiliconFlow API key |
| `openai-key` | OpenAI (optional fallback) |
| `openrouter-key` | OpenRouter (used when `LLM_BASE_URL` + `LLM_API_KEY` are not set) |

When both `LLM_BASE_URL` and `LLM_API_KEY` are set, `backend/config.py` enables `SINGLE_LLM_MODE=True` and routes all profiles to that endpoint.

**Never commit API keys.** Set and rotate them only in Azure Portal or via `az containerapp secret set`. Self-hosters supply their own keys in `.env` (see `backend/.env.example`).

## Auth0 (sign-in, D1)

Identity is **Auth0 EU** (`genequest.eu.auth0.com`); roles and verification live in the Postgres `users` table (see `docs/adr/003-auth0-eu-idp-and-account-model.md`). The SPA reads `VITE_AUTH0_*` at **build time**; the backend reads `AUTH0_*` at **runtime** on the Container App.

### Container App env vars (runtime — backend)

Set once on `gg-public` (not in the GitHub workflow — the workflow only ships a new image):

| Container App env var | Hosted value |
|---|---|
| `AUTH0_DOMAIN` | `genequest.eu.auth0.com` |
| `AUTH0_AUDIENCE` | `https://api.geneguidelines.genequest.org` |
| `SUPERADMIN_EMAILS` | `darek@genequest.org` (CSV of verified emails → superadmin on login) |

```bash
az containerapp update \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --set-env-vars \
    AUTH0_DOMAIN=genequest.eu.auth0.com \
    AUTH0_AUDIENCE=https://api.geneguidelines.genequest.org \
    SUPERADMIN_EMAILS=darek@genequest.org
```

After the auth code is on `production` and these vars are set, `GET /api/account/me` without a bearer token should return **401** (not 404 or 503).

### SPA build vars (bake-time — CI or manual)

| Variable | Hosted value |
|---|---|
| `VITE_AUTH0_DOMAIN` | `genequest.eu.auth0.com` |
| `VITE_AUTH0_CLIENT_ID` | GeneGuidelines SPA client ID (Auth0 dashboard) |
| `VITE_AUTH0_AUDIENCE` | `https://api.geneguidelines.genequest.org` (must equal `AUTH0_AUDIENCE`) |

GitHub Actions (`.github/workflows/deploy-azure.yml`) passes these when running `npm run build:public`. Defaults match the GeneQuest tenant; forks can override via repository **Variables** (`VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE`).

### Auth0 tenant checklist (one-time)

1. SPA **Allowed Callback / Logout / Web Origins** include `https://geneguidelines.genequest.org` (plus localhost ports for dev).
2. **API Access**: GeneGuidelines SPA authorized for **GeneGuidelines API** (user-delegated).
3. **Connections**: Username-Password and/or Google enabled for the SPA.
4. Optional: set tenant **Environment Tag** to **Production** in Auth0 (rate limits; does not affect tokens).

### Database migrations

Auth adds `users` and `invites` via Alembic. Run once against production Postgres after merging auth to `production`:

```bash
# From a machine that can reach the Azure Postgres host:
DB_URL='postgresql://…' alembic upgrade head
```

### ORCID (later)

Doctor verification (`ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET`, `ORCID_REDIRECT_URI`) is optional — leave unset until an ORCID app is registered; the UI hides the verify step.

## Product behavior on the hosted instance

### Supported

- Browse the disease catalog, flowcharts, doctors, therapies, and foundations (seed data + prior workflow runs).
- **`POST /api/pipeline/bootstrap-disease`** — fans out **6 workflows** (official guidelines, trials, therapies, foundations, doctor finder, living guideline) via the configured LLM provider.

### Known limitations

| Topic | Notes |
|---|---|
| **Bootstrap rate limit** | The hosted instance rate-limits bootstrap requests per client IP (see `BOOTSTRAP_RATE_LIMIT_*` in `backend/routers/pipeline.py`). Shared infrastructure — please use responsibly. |
| **API response cache** | Short in-process cache (~60 s) — after a deploy, responses may be stale briefly; use `?nocache=…` or wait. |
| **Disease summary** | `GET /api/diseases/{slug}` may lag `trialsCount` / `coverage` after a workflow; sub-resources (`/trials`, `/therapies`, …) are usually fresher. |
| **Postgres** | Set `DB_URL` on the Container App (Azure Database for PostgreSQL or equivalent). Without it the backend refuses to start. |
| **OpenRouter** | Not used as the primary provider on the hosted instance due to rate limits when bursting multiple workflows. |

## CI/CD (GitHub Actions)

Workflow: **`.github/workflows/deploy-azure.yml`**

| Step | Action |
|---|---|
| Trigger | `push` to **`production`** |
| `verify` | `npm` lint + typecheck, `pytest` (same as `ci.yml`) |
| `deploy` | `npm run build:public` (with `VITE_AUTH0_*`) → `az acr build` → `az containerapp update` |
| Image tags | `geneguidelines-backend:<7-char-SHA>` + alias `:production` |
| Smoke test | `/health` (must be ok); `/api/account/me` must not be **404** (warns on **503** if `AUTH0_*` unset on Container App) |

The workflow **does not** change Container App env vars or LLM secrets — it only deploys a new image. **Auth0 backend vars** (`AUTH0_DOMAIN`, …) are a one-time Container App setup (see § Auth0 above).

### One-time GitHub setup (foundation maintainers)

1. Create a **service principal** locally (after `az login`):

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az ad sp create-for-rbac \
  --name "github-gene-guidelines-deploy" \
  --role contributor \
  --scopes "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/geneguidelines-demo" \
  --sdk-auth
```

Copy the **entire JSON** from the output. Do **not** commit it to the repo.

2. In GitHub → **Settings → Secrets and variables → Actions** → **New repository secret**:

| Secret / variable | Value |
|---|---|
| `AZURE_CREDENTIALS` | JSON from `create-for-rbac` |
| `VITE_AUTH0_DOMAIN` (optional **Variable**) | Override SPA tenant host (default in workflow: `genequest.eu.auth0.com`) |
| `VITE_AUTH0_CLIENT_ID` (optional **Variable**) | Override SPA client ID |
| `VITE_AUTH0_AUDIENCE` (optional **Variable**) | Override API identifier |

3. **Optional:** grant the service principal **AcrPush** on registry `ggdemo45223` if `acr build` returns 403:

```bash
ACR_ID=$(az acr show --name ggdemo45223 --query id -o tsv)
az role assignment create \
  --assignee "<appId from JSON>" \
  --role AcrPush \
  --scope "$ACR_ID"
```

4. Production branch is **`production`**. Every push runs the workflow — ensure `AZURE_CREDENTIALS` is set in GitHub Actions.

### Manual deploy (emergency)

```bash
git checkout production && git pull origin production
VITE_API_URL="" \
VITE_AUTH0_DOMAIN=genequest.eu.auth0.com \
VITE_AUTH0_CLIENT_ID=eIjwuYWNv6ygMR0Ib1Z9T891qC2q9aXI \
VITE_AUTH0_AUDIENCE=https://api.geneguidelines.genequest.org \
  npm run build:public
az acr build --registry ggdemo45223 \
  --image geneguidelines-backend:manual-$(date +%Y%m%d) \
  --file Dockerfile.backend .
az containerapp update \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --image ggdemo45223.azurecr.io/geneguidelines-backend:manual-$(date +%Y%m%d)
```

Rotate the LLM key in Azure only (not in the workflow):

```bash
az containerapp secret set --name gg-public --resource-group geneguidelines-demo \
  --secrets llm-api-key="<SILICONFLOW_KEY>"
```

**Do not** set `GENEGUIDELINES_API_KEY` on the GeneQuest-hosted instance — browser-initiated bootstrap (e.g. “Add disease”) will return 401.

## Verification

```bash
# Revision, image, and env (secret values are not shown)
az containerapp show \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --query "properties.{revision:latestRevisionName,image:template.containers[0].image,env:template.containers[0].env}" \
  -o json

az containerapp secret list \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --query "[].name" -o table
```

```bash
curl -sS https://geneguidelines.genequest.org/health
curl -sS -o /dev/null -w "account/me (no token): HTTP %{http_code}\n" \
  https://geneguidelines.genequest.org/api/account/me
curl -sS "https://geneguidelines.genequest.org/api/diseases/fd/trials?nocache=$(date +%s)"
```

Expect **401** on `/api/account/me` when Auth0 is configured; **503** means `AUTH0_DOMAIN` is missing on the Container App; **404** means the auth code is not deployed yet.

## Local development vs GeneQuest-hosted instance

| | Local (`make dev` / Docker Compose) | Azure (`gg-public`) |
|---|---|---|
| Branch | feature branches → merge to `production` | **`production`** (auto-deploy) |
| Frontend | Vite :5173 → API :8000 | SPA from `/app/static` |
| Auth0 SPA | `frontend-public/.env.local` (`VITE_AUTH0_*`) | baked at `npm run build:public` in CI |
| Auth0 API | repo `.env` (`AUTH0_*`, `SUPERADMIN_EMAILS`) | Container App env vars (one-time) |
| LLM | `.env` (your own provider keys) | Container App secrets |
| Deploy | none | ACR build + `containerapp update` |

## LLM provider notes

- **GeneQuest-hosted instance**: SiliconFlow, model `google/gemma-4-31B-it`.
- **Not used on hosted instance**: self-hosted vLLM on slow CPU, OpenRouter as primary (rate limits on workflow bursts).
- **Future (not deployed)**: Azure AI Foundry with nonprofit credits, or dedicated on-prem GPU.

Self-hosters can point `LLM_*` at any vLLM-compatible endpoint; see `backend/.env.example`.

## Related files

- [README.md](../README.md) — project overview, quick start, GeneQuest Foundation
- [SECURITY.md](../SECURITY.md) — vulnerability reporting
- `Dockerfile.backend` — production image
- `backend/config.py` — `SINGLE_LLM_MODE`, LLM profiles
- `backend/routers/pipeline.py` — `bootstrap-disease`, rate limits
- `deploy/README.md` — VPS / Docker Compose self-hosting (alternative to Azure)
- `backend/.env.example` — `LLM_*` / `MODEL_PROFILE=vllm` / `AUTH0_*`
- `docs/adr/003-auth0-eu-idp-and-account-model.md` — Auth0 architecture
