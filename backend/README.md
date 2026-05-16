# `backend/` — current layout vs target

This folder is mid-migration. Some domain verticals already follow the
module-first layout described in [`../docs/ENGINEERING_VISION.md`](../docs/ENGINEERING_VISION.md)
§4.2 (target structure) and [`../docs/ROADMAP.md`](../docs/ROADMAP.md) (which
modules are in the queue); others are still flat top-level files that ship
the working POC. The split is honest and documented — nothing here is
hidden.

## At a glance

| Path | Status |
|---|---|
| `agents/` | Production layout — Pydantic AI runners, SSE trace, simple runner |
| `engine/` | Production layout — flow execution, fork/merge, ordering |
| `executors/` | Production layout — per-node-type executors (17 registered) |
| `flows/` | Production layout — flow-specific helpers |
| `routers/` | Production layout — FastAPI REST routers |
| `tools/` | Production layout — MCP server, agent tools, generated tool stubs |
| `contracts/` | Production layout — typed API contracts |
| `memory/` | Production layout — memory backends |
| `security/` | Production layout — shared security helpers |
| `tests/` | Production layout — pytest suite (314 tests) |
| **`content/`** | **Target layout — migrated module**: `api.py` + `service.py` + `repository.py` + `models.py` + `contracts.py` + `deps.py` + `tests/`. See [`content/README`](content/) for what the rest of the codebase will look like once Phase 2 completes. |
| **`shared/`** | **Target layout — foundation**: `persistence/` (SQLAlchemy 2.0 Core + Alembic baseline), `value_objects.py` (NewType aliases). Phase 2 adds `auth.py`, `observability/`, `resilience/`. |

## Flat files at the top level — slated for module migration

These will be folded into domain modules during the Phase 2 refactor (see [`../docs/ROADMAP.md`](../docs/ROADMAP.md) "Top 3 post-launch refactors"). Until then they work as-is, fully covered by integration tests.

| File | Phase 2 destination |
|---|---|
| `database.py` (2651 LOC, god-module) | Split across `{domain}/db.py` + `{domain}/repository.py` after `RunStore` Protocol introduction |
| `content_db.py` (1172 LOC) | Folded into `content/repository.py` as remaining content endpoints migrate (Disease is done; guideline document, content PRs, care pathway, catalog stats are next) |
| `content_models.py` | Folded into `content/contracts.py` |
| `doctor_catalog.py` | Foundation for the future `doctor_finder/` module |
| `doctor_finder_store.py` | Foundation for the future `doctor_finder/` module |
| `guideline_run_store.py` | Foundation for the future `guideline_run/` module |
| `guideline_pr_publish.py` | Folded into `content/service.py` |
| `guideline_prompt_profile.py` | Folded into `content/service.py` |
| `parent_pathway_schema.py` | Foundation for the future `parent_pathway/` module |
| `evidence_metrics.py`, `evidence_tiering.py` | Foundation for the future `pubmed/` module |
| `flow_pm2_normalize.py` | Same — `pubmed/normalize.py` |
| `database_flow_ensures.py` | Replaced by Alembic revisions as part of the migration |
| `models.py` | Split: API DTOs to `{domain}/contracts.py`, domain types to `{domain}/models.py`, DB-row types to `{domain}/db.py` |
| `auth.py` | Moves to `shared/auth.py` |
| `operator_settings.py` | Moves to `shared/operator_settings.py` |
| `main.py`, `config.py` | Move to `infra/main.py`, `infra/config.py` |

Per-module migration order (see [`../docs/ROADMAP.md`](../docs/ROADMAP.md)): `infra/` → `shared/` → finish `content/` → `doctor_finder/` → `parent_pathway/` → `pubmed/` → `guideline_run/` → `workflow_engine/` consolidation → `database.py` final dissolve. Each step is a separate PR with tests green between.

## Seed JSON

`seed_data.json` and the `content_*.json` files stay at this level for now; they will move under `infra/seed/` together with the `infra/` migration so the path constants only change once.

## Why not migrate everything at once

The full migration is mechanical but voluminous (~100 import statements across routers, agents, executors, tests). Pre-launch the priority is a working demo; the migration is sequenced in the post-launch window so each step lands cleanly with tests green. See [`../docs/ROADMAP.md`](../docs/ROADMAP.md) "Top 3 post-launch refactors" for the rationale.
