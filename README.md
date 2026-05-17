# GeneGuidelines

**Living clinical guidelines for rare genetic diseases** — generated and kept current by a controlled AI workflow over PubMed evidence, with every change reviewed and signed off by a senior clinician.

Powered by **Gemma 4** · 3 disease entities · PMID-grounded · `CC-BY 4.0`

```bash
docker compose up --build      # → http://localhost:5173
```

---

## The problem

PubMed indexes **~30 new rare-disease publications per day**. There are **~7,000 rare diseases**. The median lag from solid evidence appearing to incorporation into formal clinical guidelines is **~6 years**. A primary-care doctor or even a specialist surgeon cannot read enough to keep up with any single rare disease, let alone with all of them.

The result is what one family describes plainly in [the public site's About page](http://localhost:5173/#/about): a child with a rare disease can be misdiagnosed in one major hospital, scheduled for the wrong operation in a second, and saved at the last minute by one doctor with deep experience in that specific entity — *if you find them*. That should not depend on luck.

## What GeneGuidelines is

A **controlled AI workflow engine** that does three things end-to-end:

1. **Reads PubMed weekly.** A two-tier pipeline (Gemma 4 for triage + extraction, a heavier model for synthesis) turns raw abstracts into a structured corpus of evidence anchored to PMIDs.
2. **Drafts guideline updates as pull requests.** Each PR carries the diff, the citations, the AI's rationale, and an evidence-quality score. A senior clinician approves, requests changes, or rejects — and that decision is signed and dated.
3. **Surfaces three things to patients and family doctors:** the current living guideline document, a flowchart of the diagnostic pathway, and a directory of specialists ranked by published evidence in the disease.

The workflow itself is treated as a living artefact: reviewer feedback on
each PR feeds the next iteration, and the clinicians we collaborate with also
shape the workflow shape — adjusting prompts, evidence tiers, approval gates —
so it converges on how a rare-disease consortium actually works, not on how a
solo engineer guessed. The target shape is the way Javaid, Boyce,
Appelman-Dijkstra et al. drafted the [2019 FD/MAS international consensus](https://link.springer.com/article/10.1186/s13023-019-1102-9) —
structured rounds of evidence review, explicit evidence tiers, named votes —
expressed as a flow definition that any member of the consortium can edit.

The corpus that feeds those reviews isn't only PubMed. Parents can attach
the hospital discharge summary or histopathology report that never made it
into the literature, and that private context is used when drafting the next
update for their child's condition — the same case material that would
otherwise sit in a folder waiting to become a case report nobody had time to
write.

Two surfaces over one backend:

- **`frontend-public`** (`:5173`) — patients, families, clinicians: living guidelines, diagnostic pathways, specialist directory.
- **`frontend-admin`** (`:5174`) — operators: visual workflow editor, live run traces, MCP tool governance, PR review.

Backed by one **FastAPI + Pydantic AI + MCP + SQLAlchemy 2.0 Core + SQLite** service. React 18 + Vite + TypeScript + React Flow on the frontend. Server-Sent Events for live run traces. Three Gemma-compatible model profiles (`openai` / `deepseek` / `openrouter`) switchable via `MODEL_PROFILE`.

## Quick start

Two ways to run locally — pick whichever fits what you have installed.

### Containers (only Docker required)

```bash
cp backend/.env.example .env
# edit .env: OPENROUTER_API_KEY=... and MODEL_PROFILE=openrouter (or production/test)
docker compose up --build
# public  → http://localhost:5173
# admin   → http://localhost:5174
# API     → http://localhost:8000
```

### Hot-reload development (requires Python 3.12+ and Node 20+)

```bash
make install   # one-time: pip + npm + honcho
make dev       # backend + public + admin in one terminal
```

See [`CLAUDE.md`](CLAUDE.md) for the full env-var reference and [`FRONTENDS.md`](FRONTENDS.md) for build and deployment details.

## Architecture in one diagram

```
┌────────────────────┐        SSE / REST         ┌──────────────────────┐
│  frontend-public   │ ◄───────────────────────► │                      │
│  frontend-admin    │                           │   FastAPI backend    │
│  (React + Vite)    │                           │   (Pydantic AI +     │
└────────────────────┘                           │    SQLAlchemy Core)  │
                                                 └──────────┬───────────┘
                                                            │ stdio
                                                            ▼
                                                  ┌──────────────────┐
                                                  │   MCP server     │
                                                  │   (PubMed,       │
                                                  │    ClinicalTrials│
                                                  │    OpenTargets)  │
                                                  └──────────────────┘
```

Flows are **data**, not Python files: a graph of typed nodes that the engine walks step by step. Inside an *agentic* node, the AI has full freedom; *between* nodes, the engine is in charge, deterministically, along graph edges. Approvals are deterministic gates, not LLM-mediated. Every recommendation is traceable to a published source.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system overview, [`docs/ROADMAP.md`](docs/ROADMAP.md) for what is shipping next, and [`docs/ENGINEERING_VISION.md`](docs/ENGINEERING_VISION.md) for the patterns we want every new component to follow.

## Why this exists — and why every reviewer click matters

The path to AI that genuinely helps patients with rare diseases runs through **trusted human reasoning at scale**: senior clinicians making concrete decisions over concrete evidence, with the chain of inference preserved. Every guideline pull request a doctor approves, rejects, or annotates in this system — and every PMID-grounded justification the AI produces alongside it — becomes a structured record of expert clinical reasoning.

We intend that record (the **audit corpus**) to feed the training and alignment of future frontier models for medicine, openly and with the contributing experts credited. The plumbing is built into the system from day one — provenance per claim, named reviewer per decision, no anonymous mass-aggregation — so the corpus can be released without retroactive data-hygiene work.

Every reviewer decision counts twice: once for the patient on the page, once for the model that learns from the trace.

## Why Gemma 4 specifically

Three properties of the Gemma 4 family decide the architecture, not the
marketing:

1. **Edge-deployable.** The E4B variant runs on a clinician's laptop or a
   hospital server. A discharge summary uploaded by a parent is parsed,
   PII-stripped, and turned into a structured `RedactedFacts` JSON
   **without the raw text ever leaving the operator's infrastructure**. The
   cloud-hosted synthesis model only ever sees de-identified facts. That is
   not a policy promise — it is a property of the data flow.
2. **Cost profile that fits a foundation.** PubMed produces ~30 new
   rare-disease papers a day; a real living guideline workflow needs to
   triage and extract from thousands of documents a month per disease.
   Running Gemma 4 on the operator's own hardware (or a flat-rate
   inference endpoint) keeps that volume affordable, which keeps the
   evidence horizon long. A token-priced API would force triage shortcuts
   that the architecture is explicitly designed to avoid.
3. **Function-calling + structured output.** Every Gemma 4 call in the
   system returns a Pydantic-validated payload. `RedactedFacts`,
   `ClinicalFinding`, the per-paragraph PR diff schemas — the model is held
   to a contract on every step. A clinician's downstream rules can rely on
   field types, not on prompt vibes.

We are aware of the context problem in long-form clinical reasoning. The
workflow is built around it: cheap edge calls triage and extract structured
fragments, a heavier model synthesises against the *fragments* (not the raw
abstract pile), and the deterministic engine controls flow between calls.
The agent is free *inside* a node; the engine is in charge *between* nodes.

## Clinical partnerships

We are working with researchers in fibrous dysplasia and McCune–Albright syndrome at the **International FD/MAS Consortium (Leiden University Medical Center)**, **Sapienza University of Rome**, and **UCSF**, alongside a Polish network of specialists. These groups inform the design of the platform and will be among the first to use it for guideline review. Individual reviewers are credited on the documents they sign off, not in the repository front matter.

## Quality

- **328** backend + content-service tests pass
- **TypeScript strict** + ESLint clean across all four workspaces (`@gene-guidelines/ui`, `@gene-guidelines/ops`, `frontend-public`, `frontend-admin`)
- **Vitest + RTL** on the public site; **Playwright** smoke test for the critical user flow
- **Ruff + mypy + pre-commit** configured (gentle gate today, full enforcement after the Phase 2 refactor)

```bash
make ship       # the gate that must be green before a release tag
```

## Documentation

| Document | What you get |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System overview: flow engine, executors, MCP, SSE, audit corpus |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Engineering roadmap — what is clean, what is debt, three-phase plan |
| [`docs/ENGINEERING_VISION.md`](docs/ENGINEERING_VISION.md) | Full technical vision (~3000 lines): patterns, GG → Research Canvas mapping, quality tooling, risks |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records |
| [`CLAUDE.md`](CLAUDE.md) | Developer reference: env vars, conventions, commands |
| [`backend/README.md`](backend/README.md) | Backend folder layout (current vs target module-first structure) |

## What's next

The Kaggle submission ships the engine, the FD living guideline with PMID
provenance, the doctor / trial / therapy / foundation modules, the
private-context upload with Gemma 4 PII redaction, the editable workflow,
and the live "active research" projection. The next layer of the product —
the pieces we did not build in the deadline window — is concrete and short:

- **Official guideline pointer per disease.** Every disease detail page
  surfaces a "ground truth" block alongside the AI-maintained living
  document: the international consensus paper, with title, authors,
  journal, PMID, and a link to the source. For fibrous dysplasia that is
  Javaid, Boyce, Appelman-Dijkstra et al. 2019
  ([Orphanet J Rare Dis, PMID 31337488](https://link.springer.com/article/10.1186/s13023-019-1102-9));
  for MAS and Noonan the same slot is populated by a small "find-the-consensus"
  workflow that queries PubMed for the recognised guideline paper and
  promotes it to the disease record once a reviewer confirms it.
- **Three parent pathways per disease, not one.** The current
  `care_pathways` table holds a single diagnosis pathway; the design
  splits it into three flowcharts a parent can navigate independently:
  *Confirming the diagnosis and its subtype* (which test, in what order,
  what counts as definitive), *Long-term monitoring* (what to measure, how
  often, and at what threshold to escalate to a therapy decision), and
  *On treatment / after surgery* (drug-specific follow-up, post-operative
  rehabilitation, when a deviation warrants a return to the specialist).
  Schema extension: `care_pathways.kind` enum
  (`diagnosis | monitoring | post_treatment`).
- **Reviewer accounts with verification.** A clinician submits an ORCID +
  institutional affiliation, an admin approves, and the reviewer can then
  edit paragraphs by instruction ("change X because Y") or directly
  (commit-message style explanation). Disagreement between two verified
  reviewers on the same paragraph surfaces as a meta-PR — "experts
  disagree, here is why" — instead of the system pretending consensus.
- **Subscriptions for families.** A parent attaches a private context for
  their child's condition and opts in to a notification when a new trial
  matches the extracted facts, when a PR changes the recommendation for
  the documented mutation, or when a new specialist is added to the
  catalog in their region. Schema is straightforward; the policy work
  (cadence, opt-out, language, who owns the email channel) is where the
  care needs to go.

These four pieces are in `docs/produkty/geneguidelines/workbench-live-demo.md`
in the design folder; the order above is the order we ship them in.

## License

This repository is licensed under **CC-BY 4.0** (see [`LICENSE`](LICENSE)). Third-party components retain their own licences — see [`NOTICE`](NOTICE).

## Built by

[**GeneQuest Foundation**](https://genequest.org) — a Polish non-profit (KRS 0001211461) building knowledge infrastructure for rare genetic diseases. If you want to contribute, sponsor, or pilot the platform in your clinic, [we want to hear from you](mailto:kontakt@genequest.org).
