# Engineering Vision

> **Status: INTERNAL · ASPIRATIONAL · NOT A PRODUCT SPEC.**
> This is an engineering deep-dive into the *patterns* and *direction* we want to grow toward — it describes how we'd like new code to look and where the architecture is heading. It is **not** a commitment, a roadmap promise, or a list of shipped features. When something here is described as a future split, library, or capability, treat it as direction, not fact.
>
> For the authoritative description of what the system **is** today, read [`ARCHITECTURE.md`](ARCHITECTURE.md). For the product, read [`../README.md`](../README.md) and [`VISION.md`](VISION.md). The decision log lives in [`adr/`](adr/).
>
> *This file was trimmed from a ~3000-line working document on 2026-06-09; the full historical version is kept in the foundation's internal design archive.*

---

## 1. Orientation

**GeneGuidelines (GG)** is a clinical-guidelines workflow engine for rare genetic diseases (FastAPI + Pydantic AI + MCP + React + React Flow). The mission — the only north star — is **helping families** facing a diagnostic odyssey by making current, well-cited guidance reachable. Everything in this document serves that, indirectly.

Two things to hold clearly from the start:

- **GG and Research Canvas (RC) are two separate products built on a shared workflow engine.** GG renders living clinical guidelines for patients, families, and clinicians. RC is a researcher-facing exploration tool. They share the engine and the canvas UI; they do not share a product surface, and features described for one should not be assumed for the other.
- **Any reasoning/audit corpus that the engine produces is a second-order byproduct, not a driver.** It is a useful side effect of running real workflows — not the reason the architecture exists, and not "the product." The larger training-corpus and per-lab fine-tuning ambition belongs primarily to RC, and is out of scope as a design constraint for GG V1.

This doc complements [`ARCHITECTURE.md`](ARCHITECTURE.md) (what the system is). It captures the engineering *direction*: the patterns we want every new component to follow, the planned OSS split, the known risks, and the quality-tooling we're moving toward.

---

## 2. Current state (synthesis)

The codebase is a credible foundation, not a green-field project. It has a solid skeleton — an executor plugin registry, a `contracts/` folder with versioned API payloads, repositories + a factory on the public frontend, design tokens, TypeScript strict mode everywhere, and a substantial backend test suite (~300 tests, with PubMed and doctor-finder flows particularly well covered).

It also carries weight that predates the biomedical focus:

- **God-modules (backend):** `database.py`, `engine/flow_engine.py`, and `agents/runner.py` each concentrate too many concerns (persistence + schema + seed; orchestration + policy + prompt strings; agent loop + MCP + lifecycle plumbing).
- **God-components (frontend):** the largest live in `packages/ops/` — `AgentView.tsx`, `api/client.ts`, `FlowCanvas.tsx`, `NodeEditor.tsx`. `frontend-public/` and `packages/ui/` are well-distributed.
- **Test gaps:** `packages/ops` and `frontend-admin` have no tests; several executors (`approval`, `decision`, `http`, `prompt`, `agentic_prompt`, and a few biomedical ones) lack dedicated coverage.
- **Layering:** routers reach into `database` directly; some business logic lives in routers; the engine imports the `database` module instead of an injected port.
- **Legacy residue:** mostly cleaned. A handful of generic `integration_*` columns/fields survive (empty in production, kept per ADR 002), plus some Polish comments/strings in `packages/ops`. The biomedical pivot of prompts, titles, seed data, and docs is done.

> A precise file-by-file inventory goes stale fast — generate it on demand (e.g. sort sources by LOC) rather than maintaining a list here.

---

## 3. What's already good — promote it, don't break it

These patterns work and should be the template for every new component.

### 3.1 Executor plugin pattern

`backend/executors/__init__.py` exposes `EXECUTOR_REGISTRY: dict[str, type[NodeExecutor]]`. A new node type = one new file + one registry line. The contract is thin and legible:

```python
@dataclass
class NodeInput:
    node_config: dict
    context: dict
    initial_data: dict
    flow_runtime: FlowRuntimeBundle | None = None  # live store / SSE hooks for LLM nodes

@dataclass
class NodeOutput:
    data: dict
    metadata: dict = field(default_factory=dict)
    branch: str | None = None

class NodeExecutor(ABC):
    @abstractmethod
    async def execute(self, input: NodeInput) -> NodeOutput: ...
    @classmethod
    def node_type(cls) -> str: ...
```

**Direction:** evolve `node_type()` toward a declarative `NodeSpec` (see §5.3) so the frontend can render config forms automatically.

### 3.2 Versioned API contracts

`backend/contracts/agent_api_v1.py` is the model: a `*_CONTRACT_VERSION` constant, a `TypedDict` payload shape, and Pydantic models with `model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)` for forward compatibility. **Direction:** every new API surface gets its own `contracts/{domain}_v{n}.py`; the monolithic `models.py` fragments into per-domain contracts.

### 3.3 Flow-as-data + the persistence port

Flows are data, not code: nodes/edges are stored and interpreted by the engine. The single most valuable structural move is to make the engine depend on a **`RunStore` Protocol** instead of importing `database` directly. That one change unlocks testing the engine with an in-memory store, swapping SQLite for Postgres, and (later) extracting the engine as a library.

```python
class RunStore(Protocol):
    """Persistence port for the flow engine. The engine never imports `database`."""
    def get_flow_definition_nodes(self, flow_key: str) -> list[dict]: ...
    def get_flow_edges(self, flow_key: str) -> list[dict]: ...
    async def persist_node_output(self, run_id: int, node_id: str, output: dict) -> None: ...
    async def write_trace_event(self, run_id: int, event: dict) -> None: ...
    async def update_run_status(self, run_id: int, status: str, error: str | None = None) -> None: ...
```

A `SqliteRunStore` wraps existing `db.*` helpers one-to-one; an `InMemoryRunStore` satisfies the same Protocol for tests; the store is injected via FastAPI `Depends`.

### 3.4 Repositories + factory + env switch

`frontend-public/src/repositories/` exposes a `getRepositories()` factory with an `api` / `fixture` switch — every `apiFooRepository.ts` has a `fixtureFooRepository.ts` twin (easy testing, offline dev, real API in prod). **Direction:** bring this to `packages/ops`, whose API access is currently one large client module.

### 3.5 Structured-output contracts

LLM nodes emit structured output validated by Pydantic at the boundary (e.g. the PubMed article payload forwarded between pipeline stages, with `evidence_tier`, `topic_bucket`, etc.). Keep this: the LLM speaks JSON into a typed contract, never free text consumed downstream.

### 3.6 Citation / provenance lifecycle

PubMed results flow through fetch → normalize → PMID verification → tiering, carrying PMID, DOI, URLs, and an evidence tier through the contract. Provenance is a first-class field on the payload, not an afterthought. Every claim that surfaces to a clinician or family should be traceable back to a verified source. **Direction:** keep provenance attached end-to-end and surface it in the rendered guideline.

### 3.7 SSE traces through a hook

`packages/ops/src/hooks/useLiveRunTrace.ts` is the model for hermetising SSE in a hook. Inline `EventSource` elsewhere is debt. **Direction:** every new SSE consumer goes through a dedicated hook.

### 3.8 HITL gates

`approval_executor` is the human-in-the-loop pattern: a node that pauses the flow for a human decision before continuing. Reuse it for any step that needs human judgement rather than inventing new gating.

### 3.9 Foundations worth keeping

TypeScript strict mode everywhere with zero `@ts-ignore`; design tokens as CSS variables (no runtime theming engine); polymorphic `Button` with an `as` prop; pytest fixtures with autouse env-clear and `tmp_path` SQLite. Promote these conventions to new code.

---

## 4. Patterns for new components

Concrete templates to copy into new modules. The rule running through all of them: **Pydantic at the boundary, plain dataclasses in the domain, explicit SQL in repositories, thin routers.**

### 4.1 Domain vs DTO vs DB row

Three distinct shapes, never collapsed into one class:

```python
# DOMAIN — immutable, what services operate on
@dataclass(frozen=True, slots=True)
class Ticket:
    id: int
    title: str
    kind: TicketKind
    status: TicketStatus
    created_at: datetime
    def with_status(self, s: TicketStatus) -> "Ticket":
        return replace(self, status=s)

# API DTO — Pydantic, validates the HTTP boundary
class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(..., min_length=1, max_length=500)
    kind: TicketKind = "agent"

# DB ROW — TypedDict, raw SQLite shape
class TicketRow(TypedDict):
    id: int; title: str; kind: str; status: str; created_at: str
```

Boundary mappers (`*_from_request`, `*_to_response`, `*_from_row`) live at the edges. **Rule:** never use `BaseModel` as the domain object.

### 4.2 Services with constructor DI; thin routers

Business logic lives in stateless service objects with dependencies injected through the constructor; routers parse the request, call the service, format the response. Repositories are Protocols with a `Sqlite*` concrete impl and an `InMemory*` test impl. This keeps each layer independently testable and is the precondition for the engine split and the OSS extract. The `backend/content/` module (`api.py` → `service.py` → `repository.py`) is the in-repo reference for this shape — **new domains should follow it rather than adding flat files to the `backend/` root.**

### 4.3 Value objects

`NewType` aliases (`DiseaseSlug`, `PmidStr`, `RunId`, `NodeId`) for zero-cost type safety, plus Pydantic validators for formats parsed from the API (PMID = digits, 1–12 chars). Kills the "bare `str` everywhere" smell.

### 4.4 Cross-cutting decorators

```python
def retry_on_transient(attempts=3, backoff=1.0): ...   # exponential backoff on Timeout/Connection
```

```python
@asynccontextmanager
async def trace_span(name: str, runtime: FlowRuntimeBundle | None = None):
    """Emit SSE span_started / span_finished events around a unit of work."""
```

```python
def audit_call(name, *, capture_args=True, capture_result=False):
    """Generic observability decorator: records duration, args, result, error for a call.
    Useful for provenance and debugging. Any downstream corpus use is a byproduct,
    not the reason this exists — and corpus governance is an RC concern, not a GG-V1 driver."""
```

### 4.5 Test strategy

Pyramid: mostly unit (executors, repos, mappers, hooks), a layer of router/service integration on a temp SQLite, a handful of E2E (Playwright), plus property-based tests (hypothesis) for pure parsers and golden-JSON contract tests for API payloads. Three tests minimum per executor (happy path / error / edge). Direction for coverage gates is in §6.

### 4.6 Naming

Backend: `snake_case.py`, files <400 LOC, functions <50 LOC, `from __future__ import annotations`, explicit exception classes, organise by domain. Frontend: `PascalCase.tsx` components / `camelCase.ts` utils, `function Foo()` over arrow consts, `interface FooProps`, no Polish strings in new code, hooks <100 LOC. One responsibility per file; filename matches the primary export.

---

## 5. Direction: where the architecture is heading

These are intended moves, sequenced roughly. None are commitments.

### 5.1 Decouple the engine from persistence

Introduce the `RunStore` Protocol (§3.3) and wire it through the routers. This is the highest-ROI change available: low effort, unblocks engine testing, Postgres, pluggable stores, and the eventual OSS extract.

### 5.2 Split the god-modules and god-components

Once a service layer and the persistence port exist, the splits become mechanical: `database.py` → a `persistence/` package of repositories; `flow_engine.py` → runtime / orchestrator (fork-merge) / agentic-loop / prompt-builder behind a thin facade; `runner.py` → run-loop / MCP-session / SSE-publisher. On the frontend, `AgentView` / `FlowCanvas` / `NodeEditor` / the ops API client each decompose by responsibility. Do these incrementally, one unit at a time, leaning on the test suite as the safety net.

### 5.3 Declarative `NodeSpec`

Today a new node type touches a backend executor, hand-written frontend form fields, and a registry entry. A declarative `NodeSpec` (node type, display name, group, and a list of typed `NodeProperty` fields with show/hide conditions) served from `/api/node-specs` lets the frontend render config forms generically for the common case, reserving custom React fields for genuine edge cases (CodeMirror for code nodes, a RAG selector). This is what makes a large node catalog tractable.

### 5.4 Naming cleanup (`tickets` → `runs`)

`tickets` is a legacy term that doesn't fit the biomedical context. ADR 002 deliberately leaves it untouched for now. When addressed, do it as an additive migration with back-compat aliases (a `runs` table, `legacy_ticket_id` link, a v2 contract carrying both `run_id` and a `ticket_id` alias) so nothing breaks at the API boundary.

### 5.5 OSS split: `flow-engine` + `flow-kit`

The long-term direction is to extract the generic core into two libraries, leaving GG (and later RC) as thin applications on top:

- **`flow-engine`** (Python) — the engine facade, orchestrator, generic executors (decision, prompt, agentic_prompt, code, http, merge, approval, evaluation), `node_spec`, and the `RunStore` Protocol. Biomedical executors (PubMed, guidelines RAG, PMID verification, doctor-finder, parent-pathway) stay in the GG application and register themselves into the registry at bootstrap.
- **`flow-kit`** (TypeScript) — the React-Flow canvas shell, the NodeSpec-driven node editor, generic API client, the UI token set + base components, and the SSE hooks.

Prerequisites are the items above (persistence port, service layer, module splits, NodeSpec, generated TS types). This is a multi-month effort, not a weekend — sequence accordingly.

### 5.6 Clinician feedback (V1) vs governance (later)

**V1 — the model we're building:** the clinician loop is a lightweight **"useful / not useful" signal**. A clinician viewing a rendered guideline can mark items as helpful or not; those signals feed a **weighted ranking** that influences ordering and surfacing. That is the entire V1 scope. The clinician loop does **not** publish, sign, approve, or version the official guideline.

**Refresh is demand-driven, not calendar-driven** — guidelines update in response to new evidence and usage signals, not on a fixed schedule. (Context for why this matters: the lag from evidence to updated clinical guidance is roughly **~9 years** — Berg et al., *Surgery* 2025, PMID 39592333.)

**Later (V3, only if a consortium adopts the platform):** full editorial machinery — proposal/PR workflow, version history, diffs, approval/sign-off, contributor attribution, and governance — becomes worthwhile. Designing that now would be premature; the additive-migration and versioned-contract patterns leave room for it without committing to it.

### 5.7 Research Canvas is a separate product

RC reuses the engine and canvas but is its own application with its own surface (researcher-facing exploration, hypothesis trees, multi-axis literature views, and — where opted into — corpus export under per-lab governance with sharing default-off). Those are **RC** concerns. They are listed here only to clarify the boundary: **do not let RC's ambitions shape GG's V1 architecture**, and do not blur the two products.

---

## 6. Quality tooling direction

**Near-term:**
- `pyproject.toml` with Ruff (lint + format), `mypy.ini` enabling `disallow_untyped_defs` per module for new/refactored code (legacy modules relaxed), `.pre-commit-config.yaml` (ruff + ruff-format + prettier), and CI jobs for python-quality, ops/ui tests, `pip-audit`, and coverage upload.
- Fill the executor test gaps (happy/error/edge per executor).
- Polish→English sweep across `packages/ops` (comments and user-facing strings; leave biomedical content fixtures alone).

**Longer-term:**
- Storybook + visual regression for the UI / `flow-kit`.
- A coverage gate (~80% backend) once the splits land.
- Generated TS types from `/openapi.json` (types-only + hand-written fetch wrappers) to retire hand-maintained types.
- `uv` + lockfile instead of loosely pinned `requirements.txt`.
- Structured logging / tracing (OpenTelemetry over the custom SSE spans) and error tracking in production.

| Metric | Today | Direction |
|---|---|---|
| Files >800 LOC | several | 0 after splits |
| `@ts-ignore` | 0 | stays 0 |
| Backend coverage | unmeasured | measured → ~80% gate |
| Python type coverage | partial | strict per module for new code |

---

## 7. Risks and non-goals

| Risk | Mitigation |
|---|---|
| Refactoring god-modules under deadline pressure | **Hard rule:** no structural refactor during a launch window. Ship the working monolith; the tests are a refactor net only when there's time to act on a failure. |
| Treating the OSS extract as quick | It is multi-month and gated on the prerequisites in §5. Not a sprint task. |
| Engine split breaking the test suite | Do it incrementally, one module per change, test + atomic commit after each. |
| Exposing an unauthenticated admin surface | Keep admin off public links; gate with the existing `require_api_key_if_set` / edge auth. |
| Over-building governance/versioning before demand exists | Keep V1 to the useful/not-useful signal (§5.6); defer editorial machinery to V3-if-adopted. |
| Letting "corpus" reframe the mission | Corpus is a byproduct and an RC concern. The mission is helping families; design GG to that. |

**Non-goals (now):** the `tickets`→`runs` rename, the OSS extraction, full NodeSpec migration, clinician publish/approve/sign-off, calendar-based refresh, RC features inside GG, and competing with frontier labs on fundamental AI research.

---

## 8. Bottom line

The codebase is a credible base, not zero. The single highest-ROI structural move is the **`RunStore` Protocol** — it unlocks engine testing, Postgres, pluggable stores, and the eventual library split. After that, the god-module/component splits, declarative NodeSpec, and OSS extraction are largely mechanical, sequenced over months rather than days. Build new code to the §4 patterns. Keep the V1 clinician loop a lightweight signal, keep refresh demand-driven, keep RC and the corpus on the other side of a clear product boundary, and keep the mission — families first — as the only north star.

## See also

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — authoritative system overview
- [`../README.md`](../README.md), [`VISION.md`](VISION.md) — the product
- [`adr/`](adr/) — Architecture Decision Records
