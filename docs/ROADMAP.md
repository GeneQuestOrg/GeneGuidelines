# Engineering roadmap

> **Measured 2026-08-24** against the code on `main`. Every number below came from
> counting, not from memory. The detailed architectural analysis lives in
> [`ENGINEERING_VISION.md`](ENGINEERING_VISION.md); this is the short version.

The previous version of this file was written 48 hours before a hackathon deadline
and planned in units of "weeks after submission". That framing is over: the
hackathon is judged, the product runs in production for real users, and the
founder's priority is FD research rather than engine work. This version is written
for that reality — a solo maintainer who needs the codebase to stay *safe and
cheap to touch*, not to become a platform.

---

## Where this actually is

**Shipped since the last roadmap** (all of it live in production):

- **PostgreSQL + alembic** — 15 migrations, `DB_URL`, psycopg. The old SQLite /
  `tickets.db` path is gone.
- **Auth0 accounts** — roles resolved server-side, `require_superadmin` /
  `require_parent_account` / `require_verified_doctor` / `require_rating_author`
  dependency gates, and a test that fails the build if a mutating `/api` route is
  neither guarded nor explicitly declared public
  (`backend/tests/test_public_surface.py`).
- **A service layer per domain** — `account`, `content`, `disease_index`,
  `doctor_contributions`, `guidelines`, `subscriptions` each carry
  `service.py` + `repository.py` + `contracts.py`; `guidelines` and
  `doctor_contributions` also have `orm.py`. This was Phase 2's centrepiece and it
  landed.
- **A durable research queue + dedicated worker** (`backend/research_queue/`,
  `backend/worker.py`) with a monthly token budget.
- **The guidelines layer** — source shelf, synthesis with per-claim grounded
  paraphrases, suggestions, and the clinician rating loop (SIG-1) with real vote
  storage.
- **i18n** (`en` / `pl`) across the public site.

**Test counts today:** 1012 backend + content-service tests, 254 frontend-public
tests. `packages/ops` and `frontend-admin` still have **zero** tests — the same
gap the last roadmap called "highest product-risk", now two quarters older.

**The god-modules did not shrink. They grew:**

| Module | Then | Now |
|---|---:|---:|
| `backend/database.py` | 2651 | **2698** |
| `backend/engine/flow_engine.py` | 2387 | **2534** |
| `backend/content_db.py` | 1172 | **1967** |
| `backend/agents/runner.py` | 1366 | **1439** |
| `packages/ops/.../AgentView.tsx` | 2058 | **2068** |
| `packages/ops/src/api/client.ts` | 911 | **1106** |

Plus `doctor_catalog.py` (1136) and `tools/pubmed_runtime.py` (1050), which were
already large. The refactor that was "scheduled for the post-launch window" did not
happen, and the modules absorbed every new feature instead. That is the honest
headline of this document.

**The `RunStore` Protocol — the previous roadmap's "single highest-ROI item" — was
never built.** Five routers still import `backend.database` directly, and the
`tickets` table is still called `tickets`.

---

## What to do, in order

The ordering principle: **anything that makes a wrong medical claim reachable
comes first; anything that only offends an architect comes last.** A solo
maintainer with a research mission does not owe this codebase a refactor.

### 1. Tests where a mistake is invisible (highest value)

`packages/ops` and `frontend-admin` are the operator's controls — the flow editor,
the run trace, the review queue, MCP tool governance. They have no tests at all, and
they are where a wrong click changes what patients read. Start with the three
paths that write: flow save, node edit, and any review action. Not full coverage —
just the writes.

### 2. Split `content_db.py` (1967 LOC, nearly doubled)

It is the fastest-growing module and it owns seeding, schema, and queries for
content that families read. The `content/` domain next door already shows the
target shape (service / repository / contracts). Move the query layer in behind
`ContentRepository` and leave the raw-DDL seeding as the last thing to migrate.

### 3. `RunStore` Protocol (~6h, still the best hour-per-impact)

Decouple the engine from `backend.database` through a Protocol with a Postgres
implementation and an in-memory one for tests. Unlocks testing the engine without
a database and stops `database.py` growing every time the engine learns something.
It has been the recommended next step for two quarters; it is still correct.

### 4. Ruff + mypy from gentle to enforced

`pyproject.toml` ships both configs and `.pre-commit-config.yaml` ships the hooks,
but CI gates only lint + typecheck + pytest. Turning the gate on is a one-line CI
change plus a cleanup pass; do it after (2) so the cleanup happens once.

### 5. Split `flow_engine.py` and `database.py`

Only worth it if the engine keeps being developed. If the product settles and the
engine stops changing, 2500 lines of tested, working code is not a problem worth a
month.

---

## What NOT to do

- **Do not extract `@genequest/flow-engine` / `@genequest/flow-kit` as OSS
  packages.** The previous roadmap scheduled this for Q3 2026. There is no second
  consumer, no maintainer capacity for an OSS release, and the field is now full of
  well-funded agentic-workflow tooling. Extraction is cost with no return until
  someone else asks for the package.
- **Do not rename `tickets` → `runs`.** It is a cosmetic migration on a production
  medical database.
- **Do not add features to `packages/ops` before it has tests.** It is the largest
  untested surface in the repository.

---

## The constraint worth stating

This is a solo-maintained codebase behind a foundation whose actual mission is FD
research. Engine work competes directly with that mission for the same hours. The
list above is ordered so that stopping after item 1 still leaves the project safer
than it is today.
