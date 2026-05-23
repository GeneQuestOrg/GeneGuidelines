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
- **Database**: SQLite at `DB_PATH=/data/tickets.db` inside the container.
- **Seed**: on an empty database, loads `backend/content_*_seed.json` (diseases, trials, therapies, foundations).

Before building to ACR:

```bash
VITE_API_BASE_URL="" npm run build:public
az acr build --registry ggdemo45223 \
  --image geneguidelines-backend:vNEXT \
  --file Dockerfile.backend .
```

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
| **SQLite in container** | Without a persistent volume on `/data`, a new Container App revision starts with a **fresh database** (seed only). Check Azure for mounted storage — there is no Terraform definition in this repo. |
| **OpenRouter** | Not used as the primary provider on the hosted instance due to rate limits when bursting multiple workflows. |

## CI/CD (GitHub Actions)

Workflow: **`.github/workflows/deploy-azure.yml`**

| Step | Action |
|---|---|
| Trigger | `push` to **`production`** |
| `verify` | `npm` lint + typecheck, `pytest` (same as `ci.yml`) |
| `deploy` | `npm run build:public` → `az acr build` → `az containerapp update` |
| Image tags | `geneguidelines-backend:<7-char-SHA>` + alias `:production` |
| Smoke test | `curl https://geneguidelines.genequest.org/health` (up to 10× every 15 s) |

The workflow **does not** change Container App env vars or LLM secrets — it only deploys a new image.

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

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | JSON from `create-for-rbac` |

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
VITE_API_BASE_URL="" npm run build:public
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
curl -sS "https://geneguidelines.genequest.org/api/diseases/fd/trials?nocache=$(date +%s)"
```

## Local development vs GeneQuest-hosted instance

| | Local (`make dev`) | Azure (`gg-public`) |
|---|---|---|
| Branch | feature branches → merge to `production` | **`production`** (auto-deploy) |
| Frontend | Vite :5173 → API :8000 | SPA from `/app/static` |
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
- `backend/.env.example` — `LLM_*` / `MODEL_PROFILE=vllm`
