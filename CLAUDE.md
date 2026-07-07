# GeneGuidelines — developer context

Living clinical guidelines for rare genetic diseases, built by the GeneQuest Foundation. Stack: **FastAPI + Pydantic AI + MCP + PostgreSQL** backend, **React + Vite + TypeScript + React Flow** dual-frontend (`frontend-public` for patients/clinicians, `frontend-admin` for operations).

System overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Public quick-start: [`README.md`](README.md). Frontend apps: [`FRONTENDS.md`](FRONTENDS.md).

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, TypeScript, React Flow, Leaflet |
| Backend | FastAPI, Uvicorn, Python 3.12+ |
| Agent | Pydantic AI (OpenAI / DeepSeek / OpenRouter, `MODEL_PROFILE`-switched), MCP |
| Database | PostgreSQL (psycopg, `DB_URL`) + alembic migrations |
| Streaming | Server-Sent Events (run trace), REST API everywhere else |

## Layout

```
backend/
  main.py            # FastAPI app, CORS, lifespan, routers
  config.py          # Model profiles, CORS, env config
  database.py        # DB schema + seed (PostgreSQL via DB_URL)
  models.py          # Pydantic models
  agents/
    agent.py         # Agent factory; per-profile model wiring
    runner.py        # Async runner, SSE trace, 90s timeout
    simple_runner.py # Simple LLM node runner (no MCP)
    schemas.py       # Output schemas for structured prompts
  engine/            # Flow execution: fork/merge, ordering, context
  executors/         # Per-node-type executors (17 registered)
  flows/             # Flow-specific helpers (pubmed, doctor_finder, parent_pathway)
  routers/           # FastAPI REST routers
  tools/
    mcp_server.py    # MCP server (FastMCP)
    pubmed_runtime.py
    agent_tools.py
    generated/       # Generated MCP tool stubs (loader + pubmed_api)
  content_*.json     # Disease content seeds, doctor catalog
  seed_data.json     # Bootstrap data for empty DB
  tests/             # pytest

frontend-public/     # Public site
frontend-admin/      # Admin/operations panel
packages/
  ui/                # @gene-guidelines/ui
  ops/               # Shared admin widgets (FlowCanvas, NodeEditor, RunTrace)

docs/                # ARCHITECTURE.md + adr/
```

## Run

```bash
# Backend
python -m uvicorn backend.main:app --reload          # http://127.0.0.1:8000

# Public site
npm run dev:public                                   # http://localhost:5173

# Admin
npm run dev:admin                                    # http://localhost:5174
```

## Quality checks — run before any change is considered done

```bash
npm run check:dev    # pytest + frontend-public lint/typecheck + ops typecheck
```

Or one-by-one:

```bash
python3 -m pytest backend/tests -q
npm run lint
npm run typecheck
```

## npm shortcuts (from repo root)

| Script | What it runs |
|---|---|
| `npm run check:backend` | pytest backend/tests |
| `npm run check:public` | lint + typecheck frontend-public |
| `npm run check:ops` | typecheck @gene-guidelines/ops |
| `npm run check:dev` | all three above |
| `npm run dev:public` / `dev:admin` | Vite dev servers |
| `npm run build:public` / `build:admin` / `build:frontends` | Production builds |

## Environment variables

Local `.env` only — never commit secrets to `.env`, `CLAUDE.md`, or any tracked file.

| Var | Required? | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes for `production` profile | Default model profile |
| `DEEPSEEK_API_KEY` | Yes for `test` profile | DeepSeek-compatible models |
| `OPENROUTER_API_KEY` | Yes for `openrouter` profile | OpenRouter routing |
| `MODEL_PROFILE` | No (default `production`) | Switches active profile |
| `GENEGUIDELINES_API_KEY` | No | When set, protected endpoints require `Authorization: Bearer` or `X-API-Key`. SSE in the browser passes `?api_key=...`; the frontend reads `VITE_GENEGUIDELINES_API_KEY` only outside production (the key would be visible in the JS bundle). |
| `BRAVE_API_KEY` | No | Doctor Finder geo enrichment step (`df-20`): Brave Web Search + structured LLM for affiliations without ISO2. |
| `NCBI_API_KEY` | No | Raises PubMed E-utilities rate limits. |
| `DOCTOR_FINDER_GEO_MAX_AFFILIATIONS` | No (default 280) | Max unique affiliations per run (1–500). |
| `DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY` | No (default 4) | Parallel Brave queries (1–16). |
| `DOCTOR_FINDER_GEO_CONFIDENCE_MIN` | No (default 0.66) | Minimum LLM confidence to record an ISO2 (0.35–0.99). |
| `DOCTOR_FINDER_GEO_MIN_AFF_CHARS` | No (default 14) | Minimum raw affiliation length to attempt geo (8–200). |
| `DOCTOR_FINDER_RELEVANCE_LEAD_CHARS` | No (default 700) | df-1: disease-match scope limited to title + first N chars of abstract (200–12000; higher = more recall). |
| `AGENT_NO_MCP` | No | Set `1` to disable MCP (test mode). |
| `MEMORY_POSTGRES_DSN` | No | Persistent conversation memory across runs (Postgres). |

## Conventions

### Python

- Pydantic AI imports at module level — never inside threads.
- `run_agent_async`: own event loop + `asyncio.wait_for` 90-second timeout.
- Build static model instructions before kicking off the background thread; the agent should never hit the DB from that thread.
- Secrets via env vars only — never hardcode.
- Files: 200–400 lines typical, 800 max. Organise by feature/domain.
- Immutability: return new objects instead of mutating; avoid in-place updates.
- Handle errors at every level; never swallow silently.

### TypeScript

- Types in `<frontend>/src/api/client.ts` (or in `packages/ops/src/api/client.ts` for shared admin types).
- SSE handling in dedicated components.
- React state with `useState` / `useReducer`; no global stores unless asked.
- Functional components with explicit `interface` for props.

### Git

- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`.
- Never skip git hooks (`--no-verify`, `--no-gpg-sign`).
- PR summary: what, why, test plan.

### Deploy & remotes (READ before touching production)

Production is **medical** and cannot be un-shipped. Deploy is fully automated:

- **Deploy = push to the `production` branch → GitHub Actions `deploy-azure.yml` → Azure Container Apps.** That's the only code path to live. **Never deploy code by hand with `az`.** (`az` is only ever used for one-off secret/env changes such as `BRAVE_API_KEY`; that restarts the app on the *same image* and changes no code.)
- **`origin` must use the SSH alias `git@github.com-genequest:GeneQuestOrg/GeneGuidelines.git`.** The plain `github.com` host is pinned (`IdentitiesOnly yes`) to the `dmiskiew` key, which is **not** authorized on GeneQuestOrg — it fails with `Permission denied (publickey)`. The `github.com-genequest` alias uses the `genequest` key that is authorized.
- **Always push/fetch by remote name** (`git push origin production`, `git fetch origin`). **Never push by explicit URL** (`git push https://…/GeneGuidelines.git production`): a URL push updates the real remote branch but leaves the local `origin/*` tracking ref stale, so `git status` then lies with a phantom "ahead N". If you ever must push by URL, run `git fetch origin` immediately afterward to resync.
- **Before concluding anything about divergence, `git fetch origin` first.** "local production is N commits ahead of origin / live wasn't deployed from origin" is almost always a stale tracking ref — verify with a real fetch before theorizing about alternate deploy paths.
- **Verify every deploy:** `gh run watch <id> --exit-status`, then hit the live API/health to confirm the change landed.
- **Branch hygiene:** delete branches once merged (`git branch -d`, which refuses unless fully merged so no unique work is lost). Don't accumulate dozens of stale local branches or long-lived local-only branches that never reach `origin`.

## Agent pipeline (for in-editor / Claude Code use)

When you have an approved plan:

```
orchestrator → coder(s) → reviewer → tester → debugger (if FAIL)
```

- Orchestrator coordinates; does not code directly.
- Coder implements **only** the files in the plan — no scope creep.
- Reviewer runs before tests (PASS/FAIL).
- Tester runs `pytest` + `lint` + `typecheck`.
- Debugger only on FAIL, with full error context.

## Files we do not modify

- `.env`
- `*.db`, `*.db-shm`, `*.db-wal`, `*.sqlite`
- `node_modules/`, `__pycache__/`, `.pytest_cache/`, `dist/`

## Where decisions and plans live

- Architecture decisions → `docs/adr/`
- System overview → `docs/ARCHITECTURE.md`
- Update existing docs in place; don't duplicate.
