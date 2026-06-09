> [!IMPORTANT]
> **Kaggle reviewers.** There are two useful versions of GeneGuidelines:
>
> - **Current product** — active post-submission development: [public demo](https://geneguidelines.genequest.org) · [`production`](https://github.com/GeneQuestOrg/GeneGuidelines/tree/production)
> - **Frozen Kaggle submission** — exact deadline snapshot from **18 May 2026**: [tag `kaggle-submission-2026-05-18`](https://github.com/GeneQuestOrg/GeneGuidelines/tree/kaggle-submission-2026-05-18) · [public demo](https://kaggle-geneguidelines.genequest.org) · [admin demo](https://kaggle-admin-geneguidelines.genequest.org)
>
> If you are judging deadline compliance, use the frozen snapshot. If you want to see where the project is going, use the current product.

# GeneGuidelines

**Living clinical guidelines for rare genetic diseases** — generated and kept current by a controlled AI workflow over PubMed evidence. Every claim is anchored to a PubMed ID; every AI-proposed update is rated by clinicians as *useful / not useful*, a lightweight signal that ranks suggestions by how useful specialists find them.

Not a chatbot over a pile of papers. Not a static PDF that goes stale in months. A **living, audit-trailed layer** that turns *"the knowledge existed but never reached the doctor making the decision"* into a page a parent can print and bring to the visit — and that, for the first time, keeps a rare-disease guideline moving between the rare consensus updates that take [**~9 years**](https://pubmed.ncbi.nlm.nih.gov/39592333/) to land.

Powered by **Gemma 4** · 3 disease entities · PMID-grounded · `CC-BY 4.0`

```bash
docker compose up --build      # → http://localhost:5173
```

## Three people, one disease page

The reason this works is that the same engine serves three people at once, and each one *gives* something the others need:

- **A parent, just handed a diagnosis,** gets a map of what they didn't know to ask — the stage-by-stage pathway, red flags, ready-made questions for the visit, and a geo-ranked directory of doctors who have *actually treated this disease*. They can run AI research on their own child's specific question, and contribute that case back — de-identified — to widen the picture for everyone.
- **A first-contact or "in-between" clinician** — the endocrinologist or orthopaedist who meets this entity once a year and decides outside their core — gets the official guideline plus the AI's proposed updates, and rates each one *useful / not useful* in a couple of minutes.
- **A specialist or consortium** gets a running, cited diff since the last consensus — *"N new papers, 3 may change a recommendation, here's the provenance"* — ready material for the next guideline version, plus de-identified real-world cases they won't find on PubMed.

Every recommendation carries an explicit epistemic level, so no one confuses consensus with a suggestion — **that is the safety model**:

- **(a) An official guideline exists** → we render it as ground truth (e.g. Boyce et al. 2019 for FD/MAS).
- **(b) Newer or overlooked papers add something** → the AI flags it as *to consider*, for experts first; it surfaces to a family only when several clinicians vouch for it, or when it's low-risk and high-benefit.
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
2. **Proposes guideline updates for clinician review.** Each proposal carries the diff, the citations, the AI's rationale, and an evidence-quality score. Most papers warrant no change, and the system is allowed to say so. When one does, clinicians rate it *useful / not useful* — a fast signal feeding a weighted ranking where a verified specialist's vote counts for more, so the strongest suggestions rise to the top, alongside the consensus rather than overwriting it.
3. **Surfaces a whole disease in one page:** the living guideline, a decision pathway a parent can navigate, a specialist directory ranked by published evidence, active trials, therapy lines by evidence tier, and supporting foundations.

The workflow itself is a living artefact: clinician feedback — the signal plus structured notes — feeds the next iteration, and we adjust the prompts, evidence tiers, and gates so it converges on how a rare-disease consortium actually works, not on how a solo engineer guessed. The target shape is the way Javaid, Boyce, Appelman-Dijkstra et al. drafted the [2019 FD/MAS international consensus](https://link.springer.com/article/10.1186/s13023-019-1102-9) — structured rounds of evidence review, explicit evidence tiers, named votes. Full versioning with named approvals is a longer-horizon stage, for if and when a consortium adopts the platform.

The corpus that feeds those reviews isn't only PubMed: parents can attach the discharge summary or histopathology report that never made it into the literature, and that private context informs the next update for their child's condition — case material that would otherwise sit in a folder waiting to become a case report nobody had time to write.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full engine walkthrough.

## Why every clinician signal counts twice

The path to AI that genuinely helps rare-disease patients runs through **trusted human reasoning at scale**: clinicians making concrete decisions over concrete evidence, with the chain of inference preserved. Every AI proposal a clinician rates or annotates — and every PMID-grounded justification the AI produced alongside it — becomes a structured record of expert clinical reasoning, tied to a named clinician, captured with full provenance from day one.

We intend that record (the **audit corpus**) to feed the training and alignment of future medical models, openly and with contributors credited. Because provenance and attribution are built in — no anonymous mass-aggregation — the corpus can be released later without retroactive data-hygiene work. Every signal counts twice: once for the patient on the page, once for the model that learns from the trace.

## Why Gemma 4

Three properties of the Gemma 4 family decide the architecture, not the marketing:

1. **Edge-deployable.** The E4B variant runs on a clinician's laptop or a hospital server. A discharge summary uploaded by a parent is parsed, PII-stripped, and turned into a structured `RedactedFacts` JSON **without the raw text ever leaving the operator's infrastructure** — the cloud synthesis model only ever sees de-identified facts. That is not a policy promise; it is a property of the data flow.
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

## Architecture

Two surfaces over one backend:

- **`frontend-public`** (`:5173`) — patients, families, clinicians: living guidelines, diagnostic pathways, specialist directory.
- **`frontend-admin`** (`:5174`) — operators: visual workflow editor, live run traces, MCP tool governance, review queue.

Backed by one **FastAPI + Pydantic AI + MCP + SQLAlchemy 2.0 Core + SQLite** service. React 18 + Vite + TypeScript + React Flow on the frontend. Server-Sent Events for live run traces. Three Gemma-compatible model profiles (`openai` / `deepseek` / `openrouter`) switchable via `MODEL_PROFILE`.

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

Flows are **data**, not Python files: a graph of typed nodes the engine walks step by step. Inside an *agentic* node the AI has full freedom; *between* nodes the engine is in charge, deterministically, along graph edges. Gates are deterministic, not LLM-mediated, and every recommendation is traceable to a published source. Full overview in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); the patterns we want every new component to follow are in [`docs/ENGINEERING_VISION.md`](docs/ENGINEERING_VISION.md).

## Quality

- **328** backend + content-service tests pass
- **TypeScript strict** + ESLint clean across all four workspaces (`@gene-guidelines/ui`, `@gene-guidelines/ops`, `frontend-public`, `frontend-admin`)
- **Vitest + RTL** on the public site; **Playwright** smoke test for the critical user flow
- **Ruff + mypy + pre-commit** configured (gentle gate today, full enforcement after the Phase 2 refactor)

```bash
make ship       # the gate that must be green before a release tag
```

## What's next

The Kaggle submission ships the engine, the FD living guideline with PMID provenance, the doctor / trial / therapy / foundation modules, the private-context upload with Gemma 4 PII redaction, the workflow editor, and the live "active research" projection. The next layer is concrete and short:

- **Official guideline pointer per disease.** Every disease page surfaces a "ground truth" block alongside the living document: the international consensus paper, with title, authors, journal, PMID, and a source link. For fibrous dysplasia that is Javaid, Boyce, Appelman-Dijkstra et al. 2019 ([Orphanet J Rare Dis, PMID 31337488](https://link.springer.com/article/10.1186/s13023-019-1102-9)); for MAS and Noonan a small "find-the-consensus" workflow queries PubMed for the recognised paper and promotes it once a reviewer confirms it.
- **Three parent pathways per disease, not one.** Splitting the single `care_pathways` row into three flowcharts a parent navigates independently — *Confirming the diagnosis and its subtype*, *Long-term monitoring*, and *On treatment / after surgery* — via a `care_pathways.kind` enum (`diagnosis | monitoring | post_treatment`).
- **Reviewer accounts with verification.** A clinician submits an ORCID + institutional affiliation, an admin approves, and the verified reviewer's *useful / not useful* signal then carries more weight in the ranking. Richer collaboration — paragraph-level edits, explicit "experts disagree, here is why" threads, full versioning — comes later, and only where a consortium actually takes it up.
- **Subscriptions for families.** A parent attaches a private context and opts in to a notification when a new trial matches the extracted facts, when a proposal changes the recommendation for the documented mutation, or when a new specialist is added in their region. The schema is straightforward; the care goes into the policy work (cadence, opt-out, language, who owns the email channel).

The order above is the order we ship them in; see [`docs/ROADMAP.md`](docs/ROADMAP.md) for the engineering plan.

## Documentation

| Document | What you get |
|---|---|
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
