# Engineering roadmap — executive summary

What is already in place, what is debt scheduled for cleanup, and how the codebase is meant to evolve from the current Kaggle-submission state to a stable open-source workflow engine plus knowledge-base platform. The detailed analysis (~3000 lines, code snippets, mermaid diagrams) lives in [`ENGINEERING_VISION.md`](ENGINEERING_VISION.md); this document is the short version for first-time readers.

---

## TL;DR

The codebase is a credible base both for the Kaggle submission and for the longer-term **Research Canvas** product. It has a **healthy skeleton** — executor plugin pattern, contracts folder, repositories + factory on the public frontend, design tokens, TypeScript strict mode everywhere, 314 backend tests plus 14 new service-level tests for the migrated content vertical — but it also has **three god-modules on the backend** and **four god-components on the frontend** that are flagged for cleanup. The known debt is named in [`README.md`](../README.md) "Project status" so reviewers and contributors are not surprised. The OSS-library split (`@genequest/flow-engine` + `@genequest/flow-kit`) is the right strategic move and there is a real market gap, but it is a Q3 2026 project, not a weekend.

## Current state in 5 bullets

1. **Backend god-modules:** `database.py` 2651 LOC, `engine/flow_engine.py` 2387 LOC, `agents/runner.py` 1366 LOC. Plus `content_db.py` 1172, `pubmed_runtime.py` 1020. All work and are fully covered by integration tests; the refactor is scheduled for the post-launch window.
2. **Frontend god-components:** `AgentView.tsx` 2058 LOC, `ops/api/client.ts` 911 LOC, `FlowCanvas.tsx` 815 LOC, `NodeEditor.tsx` 796 LOC. All in `packages/ops/`. `frontend-public/` and `packages/ui/` are healthily distributed (max 462 LOC per file) so the refactor target is well-scoped.
3. **Tests:** 314 backend + 14 new content-service unit tests = 328 total. 78 frontend cases (44 public + 33 ui + 1 Playwright). **`packages/ops` and `frontend-admin` have no tests yet** — highest product-risk gap, top priority for Phase 2 test additions.
4. **Layering violations to address:** routers currently `import database as db`, the engine has the same coupling. The `RunStore` Protocol introduction in Phase 2 cuts both. Pydantic models and DB schema are intertwined in the legacy `models.py`; the new content module shows the target split (API DTO / domain dataclass / DB row).
5. **Quality tooling:** TypeScript strict + ESLint + Vitest + Playwright + pytest are in place. `pyproject.toml` ships gentle Ruff + mypy configs and `.pre-commit-config.yaml` ships pre-commit hooks; the strict gating moves on in Phase 2 once the god-modules are split. Storybook and coverage badges are post-launch.

## Three phases

| Phase | Window | Goal | Top 3 actions |
|---|---|---|---|
| **1. PRE-LAUNCH** | 48h before Kaggle | Working demo + minimum OSS-publication hygiene | Wire model decision (Gemma 4 via OpenRouter, with DeepSeek fallback); admin behind auth; LICENSE + SECURITY.md + NOTICE + .editorconfig |
| **2. STABILISATION** | 1–2 weeks after submission | Solid foundation for the larger architecture migration | `RunStore` Protocol; service layer per domain; models split (API / domain / DB); finish the Polish → English sweep in `packages/ops`; turn on Ruff + mypy + pre-commit gating |
| **3. REFACTOR** | Q3 2026 (~3 months) | OSS library extraction + Research Canvas readiness | Split god-modules backend + frontend; introduce declarative `NodeSpec`; rename `tickets` → `runs` migration; extract `@genequest/flow-engine` and `@genequest/flow-kit` as standalone packages |

## Top 5 pre-launch items

1. **Dependency install + green test runs.** `pip install -r requirements.txt && npm install`, then `pytest backend/tests` and `npm run check:dev` should be green before any other change.
2. **Sanity-check the seed.** `backend/seed_data.json` is already quarantined to one biomedical run + the `pubmed` and `doctor_finder` flows. A fresh `rm backend/tickets.db && python -m uvicorn backend.main:app` should boot cleanly and load the seed disease.
3. **Wire the demo model.** Commit to OpenRouter Gemma 4 free tier for the live demo, **stress-test the rate limits the evening before judging** (not during the live walkthrough). Set `MODEL_PROFILE_OPENROUTER_OVERFLOW=openai:gpt-4.1-mini` (or DeepSeek) as the fallback.
4. **Gate the admin app.** Deploy `frontend-admin` on a non-guessable hostname, set `GENEGUIDELINES_API_KEY` server-side, optionally add a basic-auth edge gate. The `require_api_key_if_set` dependency is already wired across the six routers; this is a deploy-time decision, not a code change.
5. **Minimum OSS publication hygiene.** `LICENSE` (CC-BY 4.0, per Kaggle Gemma 4 rules), `NOTICE`, `SECURITY.md`, `.editorconfig`, `.prettierrc` — all already in place. README "Project status" section honestly enumerates the remaining debt.

## Top 3 post-launch refactors (Phase 2)

1. **`RunStore` Protocol** (~6h) — decouple the engine from `backend.database` through a Protocol with a `SqliteRunStore` implementation and an `InMemoryRunStore` for tests. This single change unlocks everything else: testing the engine without a database, OSS extraction, Postgres migration, pluggable storage. The single highest-ROI hour-per-impact item in the whole roadmap.
2. **Service layer** (~10h) — separate `backend/{domain}/service.py` for each domain. Routers become thin (≤50 LOC each: parse → service → format). Easier tests with mock repos + mock LLM clients. The disease vertical already in `backend/content/` shows the target shape.
3. **Models split: API / domain / DB** (~8h) — `models.py` (currently a mixed bag of Pydantic DTOs and DB-aligned types) splits into `models/api/*` (Pydantic DTOs), `models/domain/*` (frozen, immutable dataclasses), `models/db/*` (TypedDict rows). Mapping between layers happens at boundaries via `from_request()`, `to_response()`, `from_row()` helpers.

## Top 5 patterns for new components (Research Canvas-aligned)

These five patterns are the ones the engineering vision doc spells out in detail with code snippets; new code follows them, legacy code is migrated incrementally as it gets touched.

1. **Domain models are `@dataclass(frozen=True, slots=True)`** — never Pydantic for domain. Pydantic stays at the API boundary (validate input, format output) and at structured-output contracts for AI nodes.
2. **Value objects via `NewType`** — `DiseaseSlug`, `PmidStr`, `DoiStr`, `RunId`, `ExecutionId`, `NodeId`, `FlowKey`, `ToolName`. Zero runtime cost, full static type discipline. Already shipped in `backend/shared/value_objects.py`.
3. **Service objects** — stateless `@dataclass` with dependency injection via constructor (FastAPI `Depends` per request). Easy to mock; easy to compose. Shown in `backend/content/service.py`.
4. **Repositories: Protocol + Concrete + InMemory** — services depend on a Protocol, never on a concrete `Sqla*Repo` or `InMemory*Repo`. The in-memory implementation is a legitimate production option (dev / staging / CI), not just a test helper. Shown in `backend/content/repository.py`.
5. **Decorators for cross-cutting concerns** — `@audit_call("xxx")` to feed the audit corpus (critical for the long-term Research Canvas vision and detailed in [`ENGINEERING_VISION.md`](ENGINEERING_VISION.md) §7), `@retry_on_transient(attempts=3)`, `@trace_span("flow.run")`. Decorators live in `backend/shared/observability/` and `backend/shared/resilience/`, consumed by every domain module.

## OSS library horizon (Q3 2026)

| Package | What goes in | What stays in the application |
|---|---|---|
| `@genequest/flow-engine` (PyPI, Apache 2.0) | `engine/`, generic executors (`decision`, `prompt`, `agentic_prompt`, `code`, `http`, `merge`, `approval`, `evaluation_check`), `node_spec.py`, `run_store.py` Protocol | Biomedical executors (`pubmed_authors_fetch`, `guidelines_rag`, `pmid_*`, `doctor_finder_*`, `parent_pathway_*`) — registered in app bootstrap |
| `@genequest/flow-kit` (npm, Apache 2.0) | `packages/ops/flow/`, `packages/ops/node-editor/` (after the god-component split), `packages/ui/` design tokens and the nine shared primitives, `useLiveRunTrace` hook | Domain-specific panels (`DoctorFinderPanel`, `GuidelineRunPanel`, `PathwayRunPanel`) — they consume the artefact schemas defined in their producing domain module |

**Pre-extract requirements:** RunStore Protocol (Phase 2) + service layer (Phase 2) + god-modules split (Phase 3) + declarative `NodeSpec` (Phase 3). After Phase 3 the application becomes a thin composition on top of the shared libraries.

**Why this is a real OSS deliverable:** neither n8n nor Dify has shipped a clean React-Flow + declarative `NodeSpec` library that consumers can plug into their own engine. The market gap is real.

**Workflow ↔ panel separation.** Three-layer split: a workflow produces a typed artefact, a panel renders the artefact, and the artefact schema is the contract between them. The ephemeral-vs-persistent decision is per artefact type (`DoctorResult` persistent with merge-on-upsert and protected manual fields, `GuidelineDiff` ephemeral per-run feeding the post-merge immutable versioned `Guideline`, `TrialMatch` ephemeral). Consequence for OSS extract: panels in `@genequest/flow-kit` stay generic and render artefacts by schema — swapping a workflow does not force swapping a panel.

## Open questions

### Decision in 24 hours (pre-launch)

- **Local Gemma 4 E4B via Ollama vs OpenRouter Gemma 4 free tier?** Recommendation: OpenRouter for the live demo, stress-test rate limits the evening before judging, DeepSeek as fallback.
- **Demo hosting** — Cloudflare Pages + Render, or Modal? Recommendation: Cloudflare Pages for the public frontend, Render or Fly.io for the backend, Fly.io with basic auth for the admin app.

### Decision in 1 week (Phase 2)

- **Service-layer dependency injection:** FastAPI `Depends` (minimal, idiomatic) vs `dependency-injector` (more powerful). Recommendation: stay with FastAPI `Depends` for the MVP; revisit if scope grows.
- **Migrations:** Alembic with `alembic_utils` for raw SQL vs the existing ad-hoc `_ensure_*` chain. Recommendation: Alembic. The foundation is already in place (`alembic/versions/dd31c5539990_baseline_*.py`); future schema changes go through `alembic revision --autogenerate` rather than another `_ensure_*` helper.

### Decision before Research Canvas v1 (strategic)

- **Who writes the first version of guidelines for fibrous dysplasia?** Hsiao + Dijkstra for FD; Riminucci for McCune–Albright syndrome.
- **Research Canvas governance:** per-lab opt-in (see the engineering vision doc). Sticking with the vision.
- **Audit corpus licence:** hybrid — literature-reasoning corpus open, case-specific data commercial-with-revenue-share. Sticking with the vision.
- **Per-lab continuous fine-tuning pilot:** Q3–Q4 2027, after a critical mass of audit corpus has accumulated.

## Bottom line — three sentences

1. **Pre-launch 48 hours:** no god-module refactors. Ship the monolith with `LICENSE` / English `README` / admin authentication / clean seed.
2. **1–2 weeks post-launch:** `RunStore` Protocol (~6h, highest ROI) → service layer → models split → finish Polish → English sweep in `packages/ops` → quality tooling gating. This sequence unblocks everything that follows.
3. **Q3 2026:** mechanical split of the god-modules (planned in the engineering vision doc) → declarative `NodeSpec` (eliminates ~80% of custom React config-form code) → OSS library extraction. After this both GeneGuidelines and Research Canvas become thin applications composed on the shared libraries.

**Single most important insight:** the codebase is a credible base — we are not starting from zero. The god-modules and the few remaining legacy artefacts have to go before Research Canvas can ship cleanly, but every step is mechanical once the `RunStore` Protocol lands in Phase 2.

---

## See also

- [`../README.md`](../README.md) — project status, quick start, mission
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system overview (engine, executors, MCP, SSE)
- [`ENGINEERING_VISION.md`](ENGINEERING_VISION.md) — full technical vision (~3000 lines, code snippets, diagrams)
- [`adr/`](adr/) — Architecture Decision Records
