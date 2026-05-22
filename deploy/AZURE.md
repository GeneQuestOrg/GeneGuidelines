# Azure — demo produkcyjne (GeneGuidelines)

Stan zweryfikowany **`az containerapp show`** (maj 2026, subskrypcja GeneQuest). Po każdym deployu odśwież sekcję [Stan na żywo](#stan-na-żywo).

## Publiczny adres

| Co | Wartość |
|---|---|
| **URL** | https://geneguidelines.genequest.org |
| **Health** | `GET /health` → `{"status":"ok"}` |
| **API** | Ten sam host — SPA i `/api/*` w jednym kontenerze |

## Zasoby Azure

| Zasób | Nazwa / ID |
|---|---|
| Resource group | `geneguidelines-demo` |
| Container App | `gg-public` |
| Azure Container Registry | `ggdemo45223` |
| Obraz | `ggdemo45223.azurecr.io/geneguidelines-backend:<tag>` |
| **Aktywna rewizja** | **`gg-public--0000005`** |
| **Aktywny obraz** | `ggdemo45223.azurecr.io/geneguidelines-backend:v5` |
| Poprzedni deploy merge + LLM | **`v4`** (`gg-public--0000004`, tag git `azure-deploy-v4-2026-05-19`) |
| Wcześniejszy demo (bez merga main) | **`v3`** — sprzed merga `main` na gałęź produkcyjną |

### Subskrypcja Azure (tenant)

| Pole | Wartość |
|---|---|
| Tenant | `genequest.onmicrosoft.com` — FUNDACJA GENEQUEST |
| Tenant ID | `951bbbb1-2e7a-4fca-9f8c-6109474ce866` |
| Subskrypcja (domyślna) | `Azure subscription 1` |

Custom domain `geneguidelines.genequest.org` jest podpięty do ingress Container App (szczegóły cert/DNS w portalu Azure — nie są w repo).

## Co jest w obrazie Docker

Build: **`Dockerfile.backend`** z katalogu głównego repo.

- **Backend**: FastAPI + Uvicorn na porcie **8000**, jeden worker (SSE / stan w procesie).
- **Frontend public**: `frontend-public/dist` skopiowany do **`/app/static`** — FastAPI serwuje SPA + API (CSP w `backend/main.py`).
- **Baza**: SQLite `DB_PATH=/data/tickets.db` w kontenerze.
- **Seed**: przy pustej bazie ładuje m.in. `backend/content_*_seed.json` (choroby, trials, therapies, foundations).

Przed buildem na ACR:

```bash
VITE_API_BASE_URL="" npm run build:public
az acr build --registry ggdemo45223 \
  --image geneguidelines-backend:vNEXT \
  --file Dockerfile.backend .
```

## Kod źródłowy na produkcji (gałąź Git)

| Element | Wartość |
|---|---|
| Gałąź deploy | **`demo-polish`** (push → GitHub Actions → Azure) |
| Historia | Krótko istniała gałąź `production` z tym samym workflow — produkcja wraca na `demo-polish` |
| Merge main (vLLM) | commit **`540a373`** — provider `LLM_*`, `SINGLE_LLM_MODE`, poprawki pipeline |
| Fix trials FD | commit **`375dbfe`** — prawdziwe NCT z ClinicalTrials.gov w seedzie |
| Tag snapshot | **`azure-deploy-v4-2026-05-19`** (obraz v4; v5 to ten sam kod + rebuild po fixie seed) |

### Czego **nie ma** na Azure (tylko lokalnie / inna gałąź)

Gałąź **`ai-disease-lookup`** (commit `428ed28` i nowsze) — **nie wdrożone**:

- `POST /api/pipeline/lookup-disease-metadata` (Gemma uzupełnia OMIM / gen / dziedziczenie z samej nazwy)
- Uproszczony formularz **Add disease** (jedno pole + kroki postępu)
- Pliki: `backend/services/disease_metadata_lookup.py`, `frontend-public/src/views/AddDiseaseView.tsx`, `frontend-public/src/api/lookupDisease.ts`

Na produkcji nadal widać **stary, wielopolowy** formularz pod `/#/add-disease` (gene, OMIM, inheritance, summary itd.).

## Stan na żywo

Potwierdzone `az containerapp show` (Container App `gg-public`):

```
Revision   gg-public--0000005
Image      ggdemo45223.azurecr.io/geneguidelines-backend:v5
```

## LLM na produkcji (SiliconFlow)

Backend w trybie **vLLM-compatible** (`MODEL_PROFILE=vllm` + `LLM_BASE_URL` + `LLM_API_KEY` → `SINGLE_LLM_MODE` w `backend/config.py`). Główny ruch LLM idzie przez **SiliconFlow**, nie OpenRouter.

| Zmienna (Container App) | Wartość na produkcji |
|---|---|
| `MODEL_PROFILE` | `vllm` |
| `LLM_BASE_URL` | `https://api.siliconflow.com/v1` |
| `LLM_MODEL` | `google/gemma-4-31B-it` |
| `LLM_API_KEY` | `secretref:llm-api-key` |
| `LLM_AUTH_HEADER_STYLE` | `bearer` |
| `OPENAI_API_KEY` | `sk-placeholder-unused-in-vllm-mode` (plain env — gate/API compatibility, nie używane w vLLM mode) |
| `OPENROUTER_API_KEY` | `secretref:openrouter-key` |

### Sekrety w Container App (nazwy — wartości tylko w Azure Portal / CLI)

| Secret name | Przeznaczenie |
|---|---|
| `llm-api-key` | Klucz **SiliconFlow** (`sk-…`) |
| `openai-key` | OpenAI (secret w Azure; na prod `OPENAI_API_KEY` to osobno ustawiony placeholder w env, patrz tabela wyżej) |
| `openrouter-key` | OpenRouter (używany gdy nie ma `LLM_BASE_URL` + `LLM_API_KEY`) |

Wcześniejsza konfiguracja (Vast.ai, **nieaktywna** po przełączeniu na SiliconFlow):

- `LLM_BASE_URL=http://154.42.3.11:22711/v1`
- `LLM_MODEL=gemma4:31b`
- `LLM_AUTH_HEADER_STYLE=raw`

Logika w kodzie: `backend/config.py` — gdy ustawione `LLM_BASE_URL` + `LLM_API_KEY` → `SINGLE_LLM_MODE=True`, wszystkie profile mapowane na ten endpoint.

## Zachowanie produktu na żywo

### Działa (po v4/v5)

- Przeglądanie katalogu chorób, flowchart, lekarze, terapie, fundacje (dane seed + wcześniejsze workflow).
- **`POST /api/pipeline/bootstrap-disease`** — fanout **6 workflowów** (official guidelines, trials, therapies, foundations, doctor finder, living guideline) z LLM przez SiliconFlow (~kilkadziesiąt sekund na szybkie pipeline’y).
- **FD clinical trials** (po **v5**): linki NCT prowadzą do realnych badań na clinicaltrials.gov (seed `backend/content_trials_seed.json`, commit `375dbfe`).

### Ograniczenia / znane problemy

| Temat | Opis |
|---|---|
| **Rate limit bootstrap** | Domyślnie **3** bootstrapy na IP na **24 h** (`BOOTSTRAP_RATE_LIMIT_*` w `backend/routers/pipeline.py`). Demo publiczne — nie spamować „Add disease”. |
| **Cache odpowiedzi API** | Krótki cache in-process (~60 s) — po deployu przez ~minutę można widzieć stare trials; `?nocache=…` lub odczekać. |
| **Summary choroby** | Endpoint `GET /api/diseases/{slug}` może nie odświeżyć `trialsCount` / `coverage` od razu po workflow — szczegóły w sub-zasobach (`/trials`, `/therapies`, …) są aktualniejsze. |
| **UI „research w toku”** | Brak sekcji progress z draft4 na stronie nowej choroby — do zrobienia (gałąź `ai-disease-lookup` lub osobny PR). |
| **SQLite w kontenerze** | Jeśli **nie** ma trwałego volume na `/data`, nowa rewizja Container App = **nowa baza** (tylko seed). Sprawdź w Azure czy podpięty jest Azure Files / volume — w repo nie ma definicji Terraform dla tego. |
| **HTTP do własnego vLLM** | Vast.ai porzucony (CPU ~0.6 tok/s, reasoning → puste `content`). Produkcja: SiliconFlow. |
| **OpenRouter** | Rate limity przy burst 6× workflow — nie używane jako primary po v4. |

### Trials inne niż FD

W seedzie nadal mogą być wpisy dla **MAS / Noonan** itd. — FD naprawione w `375dbfe`; reszta katalogu nie była audytowana w tej samej sesji.

## Historia rewizji (znana)

| Rewizja | Obraz | Co weszło |
|---|---|---|
| wcześniej | `v3` | `demo-polish` bez merga main, OpenRouter / placeholder, UI hackathon |
| `gg-public--0000004` | `v4` | merge `540a373`, SiliconFlow Gemma 4 31B, env `MODEL_PROFILE=vllm` |
| `gg-public--0000005` | `v5` | ten sam kod co v4 + przebudowany `dist` + seed FD trials (`375dbfe`) |

## CI/CD (GitHub Actions)

Workflow: **`.github/workflows/deploy-azure.yml`**

| Krok | Co robi |
|---|---|
| Trigger | `push` na gałąź **`demo-polish`** |
| `verify` | `npm` lint + typecheck, `pytest` (jak `ci.yml`) |
| `deploy` | `npm run build:public` → `az acr build` → `az containerapp update` |
| Tag obrazu | `geneguidelines-backend:<7-znaków-SHA>` + alias `:demo-polish` |
| Smoke | `curl https://geneguidelines.genequest.org/health` (do 10× co 15 s) |

**Nie zmienia** env ani sekretów LLM w Container App — tylko nowy obraz. Klucze SiliconFlow zostają w Azure.

### Jednorazowa konfiguracja GitHub

1. **Service principal** (u Ciebie lokalnie, po `az login`):

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az ad sp create-for-rbac \
  --name "github-gene-guidelines-deploy" \
  --role contributor \
  --scopes "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/geneguidelines-demo" \
  --sdk-auth
```

Skopiuj **cały JSON** z outputu.

2. W repo GitHub → **Settings → Secrets and variables → Actions** → **New repository secret**:

| Secret | Wartość |
|---|---|
| `AZURE_CREDENTIALS` | JSON z `create-for-rbac` |

3. **Opcjonalnie:** nadaj SP dodatkowo **AcrPush** na registry `ggdemo45223` (jeśli `acr build` zwróci 403):

```bash
ACR_ID=$(az acr show --name ggdemo45223 --query id -o tsv)
az role assignment create \
  --assignee "<appId z JSON>" \
  --role AcrPush \
  --scope "$ACR_ID"
```

4. Gałąź produkcyjna to **`demo-polish`**. Każdy push uruchamia workflow — upewnij się, że secret `AZURE_CREDENTIALS` jest ustawiony w GitHub Actions.

### Ręczny deploy (awaryjnie)

```bash
git checkout demo-polish && git pull origin demo-polish
VITE_API_BASE_URL="" npm run build:public
az acr build --registry ggdemo45223 \
  --image geneguidelines-backend:manual-$(date +%Y%m%d) \
  --file Dockerfile.backend .
az containerapp update \
  --name gg-public \
  --resource-group geneguidelines-demo \
  --image ggdemo45223.azurecr.io/geneguidelines-backend:manual-$(date +%Y%m%d)
```

Zmiana klucza LLM tylko w Azure (nie w workflow):

```bash
az containerapp secret set --name gg-public --resource-group geneguidelines-demo \
  --secrets llm-api-key="<SILICONFLOW_KEY>"
```

**Nie** ustawiaj `GENEGUIDELINES_API_KEY` na publicznym demo — wtedy bootstrap z przeglądarki dostaje 401.

## Weryfikacja (u Ciebie z `az` / `curl`)

```bash
# Rewizja + obraz + env (bez wartości sekretów)
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
# Produkcja — health + FD trials (powinno być 6 realnych NCT po v5)
curl -sS https://geneguidelines.genequest.org/health
curl -sS "https://geneguidelines.genequest.org/api/diseases/fd/trials?nocache=$(date +%s)" \
  | python3 -c "import json,sys; t=json.load(sys.stdin); print(len(t), [x.get('nct_id') for x in t[:3]])"
```

## Lokalnie vs Azure

| | Lokalnie (`make dev`) | Azure `gg-public` |
|---|---|---|
| Gałąź | feature branches → merge do `demo-polish` | **`demo-polish`** (auto-deploy) |
| Frontend | Vite :5173 → API :8000 | SPA z `/app/static` |
| LLM | `.env` — ten sam SiliconFlow co prod | sekrety Container App |
| Deploy | brak | ACR build + `containerapp update` |

## Koszty / dostawca LLM (decyzja architektoniczna)

- **Produkcja demo**: SiliconFlow, model `google/gemma-4-31B-it`, ~kilka sekund na lookup, ~30 s na fanout 6 workflowów (lokalnie zweryfikowane).
- **Odrzucone na demo**: Vast.ai (wolne CPU + reasoning), OpenRouter (rate limit przy burst).
- **Docelowo (nie wdrożone)**: Azure AI Foundry Gemma 4 na nonprofit credit; ewentualnie Mac Studio / dedykowany GPU na biurko.

## Powiązane pliki w repo

- `Dockerfile.backend` — obraz produkcyjny
- `backend/config.py` — `SINGLE_LLM_MODE`, profile LLM
- `backend/routers/pipeline.py` — `bootstrap-disease`, rate limit, `lookup-disease-metadata` (tylko po merge `ai-disease-lookup`)
- `deploy/README.md` — deploy VPS / Docker Compose (inna ścieżka niż Azure)
- `backend/.env.example` — zmienne `LLM_*` / `MODEL_PROFILE=vllm`

