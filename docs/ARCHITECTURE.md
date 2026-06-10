# GeneGuidelines — Architecture

A controlled AI workflow engine that produces and maintains **living clinical guidelines** for rare genetic diseases. The first three diseases are fibrous dysplasia (FD), McCune–Albright syndrome (MAS), and Noonan syndrome.

Two consumers:

- **Public site** (`frontend-public/`) — patients, families, primary-care clinicians: pathway diagrams, AI guideline drafts with PMID citations, specialist directory.
- **Admin site** (`frontend-admin/`) — operations: visual workflow editor, pipeline runs, tool governance, PR review of AI drafts.

One backend (`backend/`, FastAPI + Pydantic AI + MCP + SQLite).

## Core idea: controlled autonomy

A deterministic engine walks a graph of typed blocks. Some blocks are simple (call a REST API, evaluate a condition, transform data). Others are **agentic** — an AI agent has full freedom to reason and call MCP tools inside the block, but must return a structured result conforming to a Pydantic schema. The engine reads the result and decides what happens next.

```
between blocks: engine controls deterministically (graph edges, decision nodes)
inside agentic blocks: AI is free (tool calls, iteration, reasoning) → must return structured output
```

This gives clinicians and reviewers an **audit trail per block** (input, output, timestamp, branch) and a **gate at every approval step**, while still allowing the AI to do the messy work of reading evidence.

## System diagram

```
┌──────────────────┐    HTTP / SSE     ┌────────────────────┐
│ frontend-public  │ ◄──────────────► │                    │
│ frontend-admin   │                  │   FastAPI backend  │
│ (Vite + React +  │                  │   (Python, async,  │
│  React Flow)     │                  │    Pydantic AI)    │
└──────────────────┘                  └─────────┬──────────┘
                                                │ stdio
                                                ▼
                                      ┌────────────────────┐
                                      │   MCP server       │
                                      │   (FastMCP, tools) │
                                      └────────────────────┘
```

## Flow as data

Workflows are JSON in the database, not Python files. The same data drives three consumers:

| Consumer | Purpose |
|----------|---------|
| React Flow canvas (admin) | Visual editing — drag nodes, rewire edges, edit prompts |
| FlowEngine (backend) | Step-by-step execution with structured-output validation |
| YAML export/import | Git versioning, CI/CD, cross-instance deployment |

Changing a prompt, reordering steps, or adding a branch means editing data — no code changes, no redeploys.

## Plugin architecture: executors

Each block type is an independent class under `backend/executors/`, implementing a single `execute()` method. The engine doesn't know what a specific block does — it calls `execute()` and reads the `NodeOutput`. Adding a new block means creating one file in `executors/`, implementing `execute()`, and registering it in `executors/__init__.py`. The engine, the flow definition, and other blocks remain untouched.

Block types currently registered:

| Type | Purpose |
|------|---------|
| `prompt` | Simple LLM call with system prompt + Pydantic output schema |
| `agentic_prompt` | LLM with MCP tools available; agentic step-close drives structured result |
| `decision` | Conditional branching based on prior-node output (deterministic) |
| `approval` | Human-in-the-loop gate — pauses until a reviewer approves or rejects |
| `code` | Python sandbox — data transformation, normalization |
| `http_request` | Generic REST call (PubMed E-utilities, ClinicalTrials.gov, Open Targets) |
| `rag` | Knowledge-base retrieval over guideline drafts and prior runs |
| `merge` | Fan-in — combines outputs from parallel branches |
| `pubmed_authors_fetch`, `pmid_verifier`, `pmid_scrubber` | Citation lifecycle: fetch, verify resolvable, scrub bad refs |
| `guidelines_rag` | Specialised retrieval over the guideline corpus |
| `evaluation_check` | Quality gate on AI output (schema completeness, citation density) |
| `parent_pathway_*` | Care-pathway flowchart builders (Boyce-style) for the public site |
| `doctor_finder_*` | PubMed-author + ClinicalTrials → geo-resolved specialist directory |

## Structured output

Every AI block defines an output schema (Pydantic model or JSON schema). If the model returns malformed output, Pydantic AI retries up to `max_retry`. Downstream blocks read fields by name — a decision node can safely test `result.confidence >= 0.7` because `confidence` is guaranteed to be a float.

## MCP tool catalog

External capabilities (PubMed, ClinicalTrials.gov, Open Targets, geo-lookup) live behind MCP servers. The agent discovers and calls them at runtime. Each tool in the catalog has:

| Field | Role |
|-------|------|
| `category` | Scoping — load only the tools relevant to the current node |
| `execution_mode` | `AUTO` (agent calls directly) or `APPROVAL` (HITL gate before invocation) |
| `scope` | `operational` (production data) vs `builder` (codegen/PR) — isolation boundary |
| `enabled` | One-click circuit breaker — disable a tool without redeploy |

## SSE traces

When a flow runs, the backend streams events to the client over a Server-Sent Events channel: `node_started`, `tool_called`, `step_close`, `node_finished`, `approval_required`, `error`. The admin app renders this live; the public app uses it for the *Start research* progress view.

## Doctor finder pipeline

A worked example. Input: disease slug. Output: ranked, geo-resolved list of specialists with affiliations.

```
PubMed query → relevance filter (df-1) → author extraction
    → affiliation parse → country resolver (df-20: Brave Web + LLM)
    → geo-cluster → ranking → store in doctor_catalog
```

Configuration lives in env vars (`DOCTOR_FINDER_*`); see [`CLAUDE.md`](../CLAUDE.md).

## Parent-pathway pipeline

Generates a clinical pathway diagram (rendered as a Boyce-style flowchart on the public site) plus a doctor-facing AI guideline draft with PMID citations. Goes through evidence tiering, evaluation checks, and a human PR review (admin) before publication.

## Diseases in scope

| Slug | Disease | Status |
|------|---------|--------|
| `fd` | Fibrous dysplasia | Full pipeline content |
| `mas` | McCune–Albright syndrome | Skeleton (placeholder content, full pipeline runnable) |
| `noonan` | Noonan syndrome | Skeleton (same) |

New diseases are added by extending `backend/content_seed.json` and re-running the seed pipeline; no code changes needed.

## Repository layout

```
backend/
  agents/        # Pydantic AI runner, SSE trace
  engine/        # Flow execution: fork/merge, ordering, context interpolation
  executors/     # Per-node-type executors (see table above)
  flows/         # Flow definitions (parent_pathway, pubmed, doctor_finder)
  routers/       # FastAPI REST routers
  tools/         # MCP server, agent tools, PubMed runtime
  content_*.json # Disease content seeds, doctor catalog, guideline documents
  seed_data.json # Bootstrap data for empty DB
  tests/         # pytest

frontend-public/   # Vite + React + TypeScript — patient/clinician site
frontend-admin/    # Vite + React + TypeScript — operations panel
packages/
  ui/              # @gene-guidelines/ui — design tokens, shared primitives
  ops/             # Shared admin widgets (flow canvas, node editor, run trace)

docs/
  ARCHITECTURE.md  # This file
  adr/             # Architecture Decision Records
```

## Why our own engine

Existing OSS workflow platforms (n8n, Dify) have visual editors and execution engines but couple them tightly together, and their licences (n8n Sustainable Use License; Dify Apache 2.0 + extra terms) make it costly to embed in a clinical product. We need a workflow engine where:

- AI nodes are first-class, with structured-output contracts as the default
- Citations and provenance are tracked per recommendation (every claim → graph node → abstract → PMID)
- HITL approval gates are deterministic, not LLM-mediated
- The substrate is permissively licensed for clinical and foundation use

The engine and the visual editor are designed to be split into separate OSS libraries (`flow-engine` Python, `flow-kit` TypeScript) once the application has stabilised post-launch.

## Audit corpus — every reviewer decision is also training data

A consequence of how runs are recorded — typed nodes, structured outputs per step, PMID-anchored citations, human approve/reject/annotate decisions with named reviewers — is that every guideline pull request produces a clean trace of clinical reasoning: the evidence presented, the AI synthesis, the expert correction, the rationale. We call this the **audit corpus**.

Our long-term thesis is that this corpus is what is missing for AI to graduate from "summarises the literature" to "helps a clinician make the right call for *this* child with *this* mutation". We intend to release the audit corpus on terms that let frontier-model labs and open research consortia use it for training and alignment, with the contributing reviewers credited. The plumbing for this is built into the system from day one — provenance per claim, named reviewer per decision, no anonymous mass-aggregation — so the corpus can be made available without retroactive data hygiene work.

This is why the workflow + governance + provenance layer is the product, and not yet another retrieval chatbot: the reasoning we capture here is the asset.

## Roadmap

| Phase | Focus | State |
|-------|-------|-------|
| Public site | FD pathway + guideline reader + doctor finder UI | Shipping |
| Pipelines | PubMed + ClinicalTrials + parent pathway end-to-end | Shipping |
| Disease expansion | MAS + Noonan full content, fourth disease | In progress |
| OSS split | `flow-engine` and `flow-kit` libraries with clean interfaces | Planned post-launch |
| Audit corpus release | Public dataset of PR reviews + reasoning traces, reviewer-credited | Planned, schema-ready from day one |
| Per-lab fine-tuning | LoRA adapters trained on accumulated audit corpus | Planned |
