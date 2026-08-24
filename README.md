# GeneGuidelines

**Living clinical guidelines for rare genetic diseases** — generated and kept current by a controlled AI workflow over PubMed evidence. Claims taken from a paper carry its PubMed ID, and where the source shelf has nothing for a section the page says so rather than filling the gap. Clinicians can rate an AI-proposed update *useful / not useful* — a lightweight signal that ranks suggestions for the next reader. Nobody signs anything off: this is an AI draft over cited sources, not an approved guideline.

Not a chatbot over a pile of papers. Not a static PDF that goes stale in months. A **living, audit-trailed layer** that turns *"the knowledge existed but never reached the doctor making the decision"* into a page a parent can print and bring to the visit — and that, for the first time, keeps a rare-disease guideline moving between the rare consensus updates that take [**~9 years**](https://pubmed.ncbi.nlm.nih.gov/39592333/) to land.

Powered by **Gemma 4** · 7 disease entities · PMID-grounded · `CC-BY 4.0`

```bash
docker compose up --build      # → http://localhost:5173
```

## Three people, one disease page

The reason this works is that the same engine serves three people at once, and each one *gives* something the others need:

- **A parent, just handed a diagnosis,** gets a map of what they didn't know to ask — the stage-by-stage pathway, red flags, ready-made questions for the visit, and a geo-ranked directory of doctors who have *actually treated this disease*. If their disease is not in the catalogue yet, they can start the AI research for it themselves.
- **A first-contact or "in-between" clinician** — the endocrinologist or orthopaedist who meets this entity once a year and decides outside their core — gets the official guideline plus the AI's proposed updates, and rates each one *useful / not useful* in a couple of minutes.
- **A specialist or consortium** gets a running, cited diff since the last consensus — *"N new papers, 3 may change a recommendation, here's the provenance"* — ready material for the next guideline version.

Every recommendation carries an explicit epistemic level, so no one confuses consensus with a suggestion — **that is the safety model**:

- **(a) An official guideline exists** → we render it as ground truth (e.g. Boyce et al. 2019 for FD/MAS).
- **(b) Newer or overlooked papers add something** → the AI flags it as *to consider*, and it stays in the expert view. Every suggestion is written with `gate="expert"` and nothing promotes itself to the family view — promotion is meant to follow clinician signal, and until that step is built, level-(b) content simply does not reach a parent.
- **(c) No guideline exists at all** → the AI assembles a first baseline for an expert to author from. For an ultra-rare entity where Orphanet has nothing, this is the part that exists nowhere else.

## Contents

- [Why we built this](#why-we-built-this)
- [How it works](#how-it-works)
- [Why every clinician signal counts twice](#why-every-clinician-signal-counts-twice)
- [Why Gemma 4](#why-gemma-4)
- [The people backing it](#the-people-backing-it)
- [Run it locally](#run-it-locally)
- [Architecture](#architecture)
- [Quality](#quality)
- [What's next](#whats-next)
- [Get involved](#get-involved)
- [Documentation](#documentation)

## Why we built this

A dentist noticed a mass in a ten-year-old's jaw. The biopsy, read at one of the country's largest hospitals, came back **juvenile trabecular ossifying fibroma** — a tumour whose standard treatment is resection. The mass ran from his teeth into his orbital floor, so "resection" meant cutting away half a child's face. A privately-ordered genetic test found a **GNAS** mutation: the real diagnosis was **fibrous dysplasia**, for which the international consensus in children is strict — *observation, not surgery*. A senior facial surgeon abroad, knowing the corrected diagnosis, still offered to operate.

> Twice, that child was inches away from a life-altering surgery he didn't need.
> **No child should wait for the right diagnosis because they didn't have a programmer for a parent.**

None of these doctors were incompetent — no surgeon can hold seven thousand rare diseases in working memory, and the consensus governing this entity is younger than the surgeon's career. The corrected plan arrived because the family had the resources, the language, and the contacts to keep looking. That should not depend on luck. Full story: [`docs/STORY.md`](docs/STORY.md).

The numbers behind it: PubMed indexes **~30 new rare-disease publications per day** across **~7,000 rare diseases**, and the median lag from solid evidence to its incorporation into a formal guideline is **~9 years** ([Berg et al., *Surgery* 2025](https://pubmed.ncbi.nlm.nih.gov/39592333/)). And for a newly-diagnosed family the failure mode isn't *"I couldn't find the answer"* — it's *"I didn't know there was a question to ask."* That you must drive the diagnostics yourself; that a world expert in *this* disease exists; that foundations, trials, and an official guideline exist at all. So the parent view leads with a **map of what to know**, not a search box.

## How it works

A **controlled AI workflow engine**, end-to-end:

1. **Reads PubMed on a rolling basis.** A two-tier pipeline (Gemma 4 for triage + extraction, a heavier model for synthesis) turns raw abstracts into a structured corpus of evidence anchored to PMIDs. The monitor runs as densely as we want; expert review follows real demand.
2. **Proposes guideline updates for clinician review.** Each proposal carries the diff, the citations, the AI's rationale, and an evidence-quality score. Most papers warrant no change, and the system is allowed to say so. When one does, clinicians can rate it *useful / not useful* — a fast signal feeding a weighted ranking where a verified specialist's vote counts for more, so the strongest suggestions rise to the top, alongside the consensus rather than overwriting it.
3. **Surfaces a whole disease in one page:** the living guideline, a decision pathway a parent can navigate, a specialist directory ranked by published evidence, active trials, therapy lines by evidence tier, and supporting foundations.

The workflow itself is a living artefact: clinician feedback — the signal plus structured notes — feeds the next iteration, and we adjust the prompts, evidence tiers, and gates so it converges on how a rare-disease consortium actually works, not on how a solo engineer guessed. The target shape is the way Javaid, Boyce, Appelman-Dijkstra et al. drafted the [2019 FD/MAS international consensus](https://link.springer.com/article/10.1186/s13023-019-1102-9) — structured rounds of evidence review, explicit evidence tiers, named votes. Full versioning with named approvals is a longer-horizon stage, for if and when a consortium adopts the platform.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full engine walkthrough.

## Why every clinician signal counts twice

The path to AI that genuinely helps rare-disease patients runs through **trusted human reasoning at scale**: clinicians making concrete decisions over concrete evidence, with the chain of inference preserved. Every AI proposal a clinician rates — and every PMID-grounded justification the AI produced alongside it — becomes a structured record of expert clinical reasoning, tied to that clinician's account, captured with full provenance from day one. (Nobody has rated anything yet: the loop is built and waiting for its first clinicians.)

We intend that record (the **audit corpus**) to feed the training and alignment of future medical models, openly and with contributors credited. Because provenance and attribution are built in — no anonymous mass-aggregation — the corpus can be released later without retroactive data-hygiene work. Every signal counts twice: once for the patient on the page, once for the model that learns from the trace.

## Why Gemma 4

Three properties of the Gemma 4 family decide the architecture, not the marketing:

1. **Edge-deployable.** The E4B variant runs on a clinician's laptop or a hospital server, which is what makes a private-document path possible at all: parse and PII-strip locally into a structured `RedactedFacts` JSON, and let the synthesis model see only de-identified facts. We built that path and then **switched it off** (`MY_CASE_ENABLED`), because this deployment runs Gemma 4 at a hosted provider outside the EU — so the property the design depends on did not hold in production. It comes back when the redaction model runs in the EU, and not before.
2. **Cost profile that fits a foundation.** A real living-guideline workflow triages thousands of documents a month per disease. Running Gemma 4 on the operator's own hardware (or a flat-rate endpoint) keeps that volume affordable, which keeps the evidence horizon long — a token-priced API would force exactly the triage shortcuts the architecture is built to avoid.
3. **Function-calling + structured output.** Every Gemma 4 call returns a Pydantic-validated payload — `RedactedFacts`, `ClinicalFinding`, the per-paragraph diff schemas. The model is held to a contract on every step, so downstream rules rely on field types, not on prompt vibes.

We are aware of the context problem in long-form clinical reasoning, and the workflow is built around it: cheap edge calls triage and extract structured fragments, a heavier model synthesises against the *fragments*, and the deterministic engine controls flow between calls. The agent is free *inside* a node; the engine is in charge *between* nodes.

## The people backing it

Two researchers working on fibrous dysplasia and McCune–Albright syndrome — one at **Sapienza University of Rome**, one at **UCSF** — have agreed to be among the first to try the platform once it's ready, alongside a Polish network of specialists. One of them, after warning us about failure modes he has seen in clinical AI elsewhere, offered to help us avoid them. From there we are building toward a wider reviewer network; reviewers are credited on the documents they review, not in the repository front matter.

## Run it locally

Two ways to run — pick whichever fits what you have installed.

### Containers (only Docker required)

```bash
cp backend/.env.example .env
# edit .env: pick a MODEL_PROFILE and give it a key, e.g.
#   MODEL_PROFILE=openrouter + OPENROUTER_API_KEY=...
#   MODEL_PROFILE=ollama     + a local Gemma on :11434 (no key, no cloud)
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

## Architecture

Two surfaces over one backend:

- **`frontend-public`** (`:5173`) — patients, families, clinicians: living guidelines, diagnostic pathways, specialist directory.
- **`frontend-admin`** (`:5174`) — operators: visual workflow editor, live run traces, MCP tool governance, review queue.

Backed by one **FastAPI + Pydantic AI + MCP + SQLAlchemy 2.0 (ORM + Core) + PostgreSQL** service (`DB_URL`, psycopg). React 18 + Vite + TypeScript + React Flow on the frontend. Server-Sent Events for live run traces. Production runs **`MODEL_PROFILE=vllm`** (Gemma 4 at a hosted OpenAI-compatible endpoint — SiliconFlow). The other profiles are `production` (the code's own fallback), `test`, `openrouter`, `synthesis` and `ollama` — the last one points at a local Gemma, which is how the model swap gets tested.

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

Flows are **data**, not Python files: a graph of typed nodes the engine walks step by step. Inside an *agentic* node the AI has full freedom; *between* nodes the engine is in charge, deterministically, along graph edges. Gates are deterministic, not LLM-mediated, and a claim taken from a paper is traceable to it by PMID — with sections that have no source on the shelf saying so instead. Full overview in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); the patterns we want every new component to follow are in [`docs/ENGINEERING_VISION.md`](docs/ENGINEERING_VISION.md).

## Quality

- **1012** backend + content-service tests pass
- **TypeScript strict** + ESLint clean across all four workspaces (`@gene-guidelines/ui`, `@gene-guidelines/ops`, `frontend-public`, `frontend-admin`)
- **Vitest + RTL** on the public site; **Playwright** smoke test for the critical user flow
- **Ruff + mypy + pre-commit** configured (gentle gate today, full enforcement after the Phase 2 refactor)

```bash
make ship       # the gate that must be green before a release tag
```

## What's next

Shipping today: the engine, seven disease entities with PMID-grounded synthesis and per-claim source paraphrases, the doctor / trial / therapy / foundation modules, the official-guideline pointer, disease alerts with double opt-in, the workflow editor, and the live "active research" projection. Since the first release the scope has narrowed on purpose — doctors, guidelines, what the AI finds in PubMed, trials, foundations, therapies — and the private-document upload is switched off (see *Why Gemma 4*).

What is genuinely still open:

- **Three parent pathways per disease, not one.** The column exists (`care_pathways.kind`: `diagnosis | monitoring | post_treatment`); the content does not. A parent should navigate *Confirming the diagnosis and its subtype*, *Long-term monitoring* and *On treatment / after surgery* separately, instead of one flowchart that mixes all three.
- **Richer clinician collaboration.** Verified-clinician accounts and the weighted *useful / not useful* signal are in. Paragraph-level edits, explicit "experts disagree, here is why" threads and full versioning are not — and they only get built where a consortium actually takes the platform up.
- **Coverage that a family can rely on.** Seven entities is a demonstration, not a service. Widening it is a question of research budget per disease, not of engine work.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the engineering plan.

## Get involved

GeneGuidelines is open source (CC-BY 4.0) and built by a non-profit — every kind of help moves it forward:

- **Clinicians & specialists** — review a disease you know and rate the AI's proposed updates *useful / not useful*. A few minutes; your signal ranks suggestions for the next doctor who reads them. [Email us](mailto:kontakt@genequest.org) to get set up.
- **Developers** — the engine, the flow kit, and both frontends are open. Issues and PRs welcome; start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`CLAUDE.md`](CLAUDE.md).
- **Researchers** — pilot the platform on a disease you work on, and help shape the engine for your own questions. [Reach out](mailto:kontakt@genequest.org).
- **Foundations & sponsors** — help us widen disease coverage and the specialist directory. We're a registered non-profit (KRS 0001211461); [let's talk](mailto:kontakt@genequest.org).

Disease not in the catalogue yet? Anyone can request one from the [live site](https://geneguidelines.genequest.org) — it fans out the AI workflows for that entity and the page fills in as each one lands.

## Documentation

| Document | What you get |
|---|---|
| [`VISION.md`](VISION.md) | Where the product is heading and why (condensed public vision) |
| [`docs/STORY.md`](docs/STORY.md) | The family story behind the project |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System overview: flow engine, executors, MCP, SSE, audit corpus |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Engineering roadmap — what is clean, what is debt, three-phase plan |
| [`docs/ENGINEERING_VISION.md`](docs/ENGINEERING_VISION.md) | Full technical vision: patterns, GG → Research Canvas mapping, quality tooling, risks |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records |
| [`CLAUDE.md`](CLAUDE.md) | Developer reference: env vars, conventions, commands |
| [`backend/README.md`](backend/README.md) | Backend folder layout (current vs target module-first structure) |

## License

This repository is licensed under **CC-BY 4.0** (see [`LICENSE`](LICENSE)). Third-party components retain their own licences — see [`NOTICE`](NOTICE).

## Built by

[**GeneQuest Foundation**](https://genequest.org) — a Polish non-profit (KRS 0001211461) building knowledge infrastructure for rare genetic diseases. If you want to contribute, sponsor, or pilot the platform in your clinic, [we want to hear from you](mailto:kontakt@genequest.org).
