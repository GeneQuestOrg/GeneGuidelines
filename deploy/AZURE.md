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
| **Subscription** | `Azure subscription 1` (foundation tenant — see § Ops discovery) |
| Resource group | `geneguidelines-demo` |
| Container App | `gg-public` |
| Azure Container Registry | `ggdemo45223` |
| Postgres Flexible Server | `gg-pg-prod-07674` |
| Postgres database | `geneguidelines` (app user `ggapp`) |
| Image | `ggdemo45223.azurecr.io/geneguidelines-backend:<tag>` |

> Resource group and registry names retain a `-demo` suffix from early hosting; the instance serves the public GeneGuidelines product, not a throwaway prototype.

## Ops discovery — finding what we have on Azure

This section records **how maintainers locate** foundation resources when returning after a break, onboarding a collaborator, or preparing a deploy. Names are not secrets; connection strings and API keys live only in Azure.

### 1. Log in to the right tenant

GeneGuidelines production lives in the **GeneQuest Foundation** Azure AD tenant, not a personal Microsoft account.

```bash
az login                    # pick genequest.onmicrosoft.com if prompted
az account show -o table    # expect TenantDisplayName ≈ FUNDACJA "GENEQUEST …"
```

If `az containerapp show … geneguidelines-demo` returns **ResourceGroupNotFound**, you are on the wrong subscription. List and switch:

```bash
az account list -o table
az account set --subscription "<Azure subscription 1 id>"
```

As of 2026-06-20 the foundation subscription id is `e80c0793-8fcd-419f-8941-5dbe93598b39`. Other subscriptions on the same machine (e.g. personal **Microsoft Azure Sponsorship**) do **not** host `geneguidelines-demo`.

### 2. Inventory resource groups and Postgres

```bash
az group list --query "[?contains(name,'gene') || contains(name,'gg')].{name:name,location:location}" -o table

az postgres flexible-server list \
  --query "[].{name:name,rg:resourceGroup,fqdn:fullyQualifiedDomainName,state:state}" -o table
```

Expected GeneGuidelines stack:

| Resource group | What lives there |
|---|---|
| `geneguidelines-demo` | `gg-public` Container App, ACR `ggdemo45223`, Postgres `gg-pg-prod-07674` |
| `rg-genequest-analytics` | Umami analytics Postgres `gq-umami-pg-8822` (separate product — not GeneGuidelines DB) |

Postgres host (public, firewall-restricted): `gg-pg-prod-07674.postgres.database.azure.com`, region **polandcentral**, version **16**, SKU **B1ms**.

### 3. Where names are documented in this monorepo

| Source | What it tells you |
|---|---|
| **This file** (`deploy/AZURE.md`) | Canonical live URLs, Container App / ACR names, Auth0, CI/CD |
| [`docs/produkty/geneguidelines/archiwum/realizacja-pre-v1-2026-06/architektura/plan-postgres-migration.md`](../../docs/produkty/geneguidelines/archiwum/realizacja-pre-v1-2026-06/architektura/plan-postgres-migration.md) | Postgres provisioning history (2026-05-24), migration from SQLite, credential backup note |
| [`docs/produkty/geneguidelines/archiwum/realizacja-pre-v1-2026-06/roadmap.md`](../../docs/produkty/geneguidelines/archiwum/realizacja-pre-v1-2026-06/roadmap.md) | Sprint 0.5 Postgres DONE checklist |
| [`GeneGuidelinesObserver/deploy/AZURE.md`](../../GeneGuidelinesObserver/deploy/AZURE.md) | Observer app on same Postgres server (different database) |
| [`docs/produkty/geneguidelines/eksperymenty/experiments-k1-add-disease-local.md`](../../docs/produkty/geneguidelines/eksperymenty/experiments-k1-add-disease-local.md) | **Safety rule:** never point local `.env` at `gg-pg-prod-07674` for experiments |

Repo search tip: `rg 'gg-pg-prod|geneguidelines-demo|gg-public' docs/ GeneGuidelines/deploy/`.

### 4. Read live Container App state (no secrets)

```bash
# Running image + revision (compare to origin/production SHA)
az containerapp show \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --query "properties.{revision:latestRevisionName,image:template.containers[0].image}" \
  -o json

# Env var names and plain-text values (Auth0 domain, etc.)
az containerapp show \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --query "properties.template.containers[0].env[?name=='DB_URL' || contains(name,'AUTH0') || name=='SUPERADMIN_EMAILS']" \
  -o json

# Secret names only
az containerapp secret list \
  --name gg-public \
  --resource-group geneguidelines-demo \
  -o table
```

Expected secrets on `gg-public`: `db-url`, `llm-api-key`, `openrouter-key` (and optionally `openai-key`).

### 5. Get the production `DB_URL` (for backup / migration only)

**Do not** commit the output. Prefer Azure CLI over copying from sibling repos' `.env` files.

```bash
export PROD_DB_URL=$(az containerapp secret show \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --secret-name db-url \
  --query "value" -o tsv)

# Sanity check (no password printed)
echo "$PROD_DB_URL" | sed 's/:[^:@]*@/:***@/'
```

### 6. Postgres firewall — connect from your machine

The server allows Azure services (`0.0.0.0` rule) and named dev IPs. Your laptop IP is **not** open by default.

```bash
MYIP=$(curl -sS ifconfig.me)
az postgres flexible-server firewall-rule list \
  --resource-group geneguidelines-demo \
  --name gg-pg-prod-07674 -o table

az postgres flexible-server firewall-rule create \
  --resource-group geneguidelines-demo \
  --name gg-pg-prod-07674 \
  --rule-name "dev-$(whoami)-$(date +%Y%m%d)" \
  --start-ip-address "$MYIP" \
  --end-ip-address "$MYIP"
```

Remove temporary rules when done. Credential backup from the 2026-05 migration session was noted at `/tmp/gg-pg-prod/credentials.env` (mode 600) — long-term storage should be Bitwarden / Azure Key Vault, not git.

### 7. Inspect production database shape

```bash
psql "$PROD_DB_URL" -c "\dt"
psql "$PROD_DB_URL" -c "SELECT to_regclass('public.alembic_version');"
psql "$PROD_DB_URL" -c "SELECT slug FROM diseases ORDER BY slug;"
```

**Known state (verified 2026-06-20):** schema created by `init_db()` at Postgres cutover — **28 tables**, **no `alembic_version` row** until first Alembic run. Runtime data: 3 diseases (`fd`, `mas`, `noonan`), 5 `content_prs`. Code on `origin/main` expects **7 additional migrations** (auth, research queue, guidelines layer, bibliography).

### 8. Code vs production branch gap

Deploy branch is **`production`**, development is **`main`**. Compare before pushing:

```bash
git fetch origin
git log origin/production..origin/main --oneline | wc -l   # commits not yet live
git log origin/production -1 --oneline
git log origin/main -1 --oneline
```

As of 2026-06-20: production image tag `3907376` (~12 Jun); `main` was **65 commits ahead**. Push `git push origin main:production` triggers `.github/workflows/deploy-azure.yml` — but **run DB migrations first** (§ Database migrations below).

### 9. Backup and test migration locally (recommended before prod)

```bash
mkdir -p /tmp/gg-migration-test
pg_dump "$PROD_DB_URL" --no-owner --no-acl -F c \
  -f /tmp/gg-migration-test/prod-$(date +%Y%m%d).dump

# Restore into local Docker Postgres (see docker-compose.yml credentials)
createdb geneguidelines_prod_mirror   # or via docker exec on geneguidelines-postgres-1
pg_restore --no-owner --no-acl \
  -d "postgresql://ggapp:testpass@localhost:5432/geneguidelines_prod_mirror" \
  /tmp/gg-migration-test/prod-YYYYMMDD.dump

cd GeneGuidelines
export DB_URL="postgresql://ggapp:testpass@localhost:5432/geneguidelines_prod_mirror"
alembic stamp dd31c5539990    # baseline tables already exist — do NOT run baseline upgrade()
alembic upgrade head
psql "$DB_URL" -c "SELECT version_num FROM alembic_version;"
```

Tested successfully 2026-06-20: all 7 pending migrations applied; seed data unchanged; `diseases.listed` defaulted to `1`.

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

### Email alerts (disease subscriptions, double opt-in)

Backend sends confirmation links via **Resend**. Set once on `gg-public` (runtime — not in the GitHub workflow):

| Container App env var | Hosted value |
|---|---|
| `EMAIL_FROM` | `GeneGuidelines <info@genequest.org>` (must be a verified sender in Resend) |
| `PUBLIC_APP_URL` | `https://geneguidelines.genequest.org` (redirect after confirm) |
| `API_PUBLIC_URL` | `https://geneguidelines.genequest.org` (confirm/unsubscribe links — same host as SPA; there is no separate `api.` subdomain) |
| `RESEND_API_KEY` | `secretref:resend-api-key` |

| Secret name | Purpose |
|---|---|
| `resend-api-key` | Resend API key |

```bash
az containerapp secret set --name gg-public --resource-group geneguidelines-demo \
  --secrets resend-api-key="<RESEND_API_KEY>"

az containerapp update \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --set-env-vars \
    EMAIL_FROM='GeneGuidelines <info@genequest.org>' \
    PUBLIC_APP_URL=https://geneguidelines.genequest.org \
    API_PUBLIC_URL=https://geneguidelines.genequest.org \
    RESEND_API_KEY=secretref:resend-api-key
```

After deploy, run `alembic upgrade head` if the subscription migration (`b8e3f1a2c4d5`) is not yet on prod Postgres.

### Container App secrets (names only — values live in Azure)

| Secret name | Purpose |
|---|---|
| `llm-api-key` | SiliconFlow API key |
| `openai-key` | OpenAI (optional fallback) |
| `openrouter-key` | OpenRouter (used when `LLM_BASE_URL` + `LLM_API_KEY` are not set) |
| `resend-api-key` | Resend (subscription confirmation emails) |

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
4. **Email claim on the access token** (required for `SUPERADMIN_EMAILS` + non-blank account emails). Auth0 access tokens omit `email` and silently drop non-namespaced custom claims, so add a **Login Action** (Actions → Triggers → post-login):

   ```js
   exports.onExecutePostLogin = async (event, api) => {
     const ns = "https://genequest.org";
     api.accessToken.setCustomClaim(`${ns}/email`, event.user.email);
     api.accessToken.setCustomClaim(`${ns}/email_verified`, event.user.email_verified);
   };
   ```

   The backend reads `https://genequest.org/email` (falling back to bare `email`) in `backend/account/jwt.py`. Without this Action, superadmin-by-email never matches and users provision with a blank email.
5. Optional: set tenant **Environment Tag** to **Production** in Auth0 (rate limits; does not affect tokens).

### Database migrations

Migrations are **not** applied by the Container App or GitHub Actions deploy. Run them manually from a machine that can reach Azure Postgres (firewall rule + `az login` — see § Ops discovery).

**Critical:** production Postgres was bootstrapped with `init_db()` (May 2026 cutover). The Alembic **baseline** revision (`dd31c5539990`) creates tables that **already exist**. Running `alembic upgrade head` alone will fail on `relation "diseases" already exists`.

Correct procedure:

```bash
# 1. Backup
pg_dump "$PROD_DB_URL" --no-owner --no-acl -F c -f /tmp/gg-pre-migrate-$(date +%Y%m%d).dump

# 2. From GeneGuidelines repo root, on main (or the revision you are deploying):
export DB_URL=$(az containerapp secret show \
  --name gg-public --resource-group geneguidelines-demo \
  --secret-name db-url --query "value" -o tsv)

alembic stamp dd31c5539990   # mark baseline as applied without re-running DDL
alembic upgrade head         # feb15ef6e670 … a2d6f4b1c9e7 (users, invites, listed, research_jobs, …)

psql "$DB_URL" -c "SELECT version_num FROM alembic_version;"
# expect: a2d6f4b1c9e7
```

Migration chain (2026-06): `dd31c5539990` baseline → `feb15ef6e670` users → `a1c4d9f2b3e8` invites → `c7e2a9f4d6b1` `diseases.listed` → `b4f8a1c2d9e3` research_jobs → `e5a3c1f7d2b9` doctor_contributions → `f1a7c3e9b8d2` guidelines layer → `a2d6f4b1c9e7` analyzed bibliography.

**Order for a full release:** backup → `stamp` + `upgrade head` → `git push origin main:production` → smoke test (`/health`, `/api/account/me` → 401, new guideline views, one Auth0 login).

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

## Dedicated research worker (`gg-worker`)

Research (the 6-workflow disease bootstrap) runs in a **separate** Container App so
the web process never blocks its event loop on long PubMed/LLM work:

| App | Role | `RESEARCH_QUEUE_MAX_CONCURRENT` |
|---|---|---|
| `gg-public` | web — admits jobs + serves status from Postgres | **0** (runs zero research workers) |
| `gg-worker` | dedicated processor — claims `research_jobs` and runs them | **1** (this process is the pool) |

Both share the **same Postgres** (`secretref:db-url`) and the **same image tag**.
The worker has **no ingress** (it never serves HTTP) and runs `python -m backend.worker`.
The deploy workflow rolls `gg-worker` to the same tag as `gg-public`, but only **if it
already exists** — provisioning is the one-time manual step below.

### Token budget guard

The worker appends one `token_usage` row per successful LLM call (`backend/research_queue/token_budget.py`)
and pauses claiming new disease jobs once `SUM(total_tokens)` for the current month
reaches `RESEARCH_TOKEN_BUDGET_MONTHLY` (`0`/unset = unlimited). Set the cap on **both**
apps so the web `/api/research/budget` readout and the worker guard agree. Live readout:
`GET /api/research/budget` → `{"limit","spent","remaining","window","blocked"}`.

### One-time provisioning

Requires the `token_usage` migration applied first (see § Database migrations) — the
worker queries it on startup. Mirror `gg-public`'s registry auth (ACR admin) and the
LLM/DB/NCBI secrets onto the new app. The container `command` needs dash args (`-m`),
which the `az ... --command` flag cannot parse, so create from a JSON/YAML spec:

```bash
RG=geneguidelines-demo
# Pull the values to mirror (do not print them):
S_DB=$(az containerapp secret show -n gg-public -g $RG --secret-name db-url --query value -o tsv)
S_LLM=$(az containerapp secret show -n gg-public -g $RG --secret-name llm-api-key --query value -o tsv)
S_NCBI=$(az containerapp secret show -n gg-public -g $RG --secret-name ncbi-api-key --query value -o tsv)
S_OR=$(az containerapp secret show -n gg-public -g $RG --secret-name openrouter-key --query value -o tsv)
ACR_PWD=$(az acr credential show -n ggdemo45223 --query "passwords[0].value" -o tsv)
TAG=$(az containerapp show -n gg-public -g $RG --query "properties.template.containers[0].image" -o tsv | sed 's/.*://')

# Write a 0600 spec (JSON is valid YAML; lets the command carry "-m"):
python3 - "$S_DB" "$S_LLM" "$S_NCBI" "$S_OR" "$ACR_PWD" "$TAG" > /tmp/gg-worker.json <<'PY'
import json, sys
db, llm, ncbi, orr, acr, tag = sys.argv[1:7]
print(json.dumps({
  "location": "Poland Central",
  "properties": {
    "managedEnvironmentId": "/subscriptions/<SUB_ID>/resourceGroups/geneguidelines-demo/providers/Microsoft.App/managedEnvironments/gg-env",
    "configuration": {
      "activeRevisionsMode": "Single",
      "secrets": [
        {"name":"db-url","value":db},{"name":"llm-api-key","value":llm},
        {"name":"ncbi-api-key","value":ncbi},{"name":"openrouter-key","value":orr},
        {"name":"acr-password","value":acr}],
      "registries": [{"server":"ggdemo45223.azurecr.io","username":"ggdemo45223","passwordSecretRef":"acr-password"}]
    },
    "template": {
      "containers": [{
        "name":"gg-worker",
        "image":f"ggdemo45223.azurecr.io/geneguidelines-backend:{tag}",
        "command":["python","-m","backend.worker"],
        "resources":{"cpu":1.0,"memory":"2.0Gi"},
        "env":[
          {"name":"MODEL_PROFILE","value":"vllm"},
          {"name":"LLM_BASE_URL","value":"https://api.siliconflow.com/v1"},
          {"name":"LLM_MODEL","value":"google/gemma-4-31B-it"},
          {"name":"LLM_AUTH_HEADER_STYLE","value":"bearer"},
          {"name":"LLM_API_KEY","secretRef":"llm-api-key"},
          {"name":"OPENAI_API_KEY","value":"sk-placeholder-unused-in-vllm-mode"},
          {"name":"OPENROUTER_API_KEY","secretRef":"openrouter-key"},
          {"name":"DB_URL","secretRef":"db-url"},
          {"name":"NCBI_API_KEY","secretRef":"ncbi-api-key"},
          {"name":"RESEARCH_QUEUE_MAX_CONCURRENT","value":"1"},
          {"name":"RESEARCH_TOKEN_BUDGET_MONTHLY","value":"100000000"}]
      }],
      "scale":{"minReplicas":1,"maxReplicas":1}
    }
  }
}, indent=2))
PY
chmod 600 /tmp/gg-worker.json
az containerapp create -n gg-worker -g $RG --yaml /tmp/gg-worker.json
rm -f /tmp/gg-worker.json   # contains secrets

# Flip the web app to admit-only + same budget (its own revision):
az containerapp update -n gg-public -g $RG \
  --set-env-vars RESEARCH_QUEUE_MAX_CONCURRENT=0 RESEARCH_TOKEN_BUDGET_MONTHLY=100000000
```

Verify: `az containerapp logs show -n gg-worker -g $RG --tail 20 --type console` →
`scheduler started (max_concurrent=1) — waiting for jobs`; then a bootstrap
(`POST /api/pipeline/bootstrap-disease`) is admitted by `gg-public` (`status:queued`)
and processed by `gg-worker`, with `/api/research/budget` `spent` climbing.

### Rollback

Restore today's behavior in two commands: re-enable in-process research on the web app
and stop the worker.

```bash
az containerapp update -n gg-public -g geneguidelines-demo --remove-env-vars RESEARCH_QUEUE_MAX_CONCURRENT
az containerapp update -n gg-worker -g geneguidelines-demo --min-replicas 0 --max-replicas 0   # or: az containerapp delete -n gg-worker -g geneguidelines-demo
```

The `token_usage` table and migration are additive and harmless to leave in place.

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
