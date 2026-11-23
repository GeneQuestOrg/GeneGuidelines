# Labs

A lab answers one product question on data instead of intuition: which model, which prompt, which setting. It runs the product's own code with real model calls against inputs frozen to disk, and applies a decision rule written down before the first paid call. A lab never changes production and never writes to a database; whatever it learns reaches the product as an ordinary, reviewed change.

## What every lab does

- **Runs the product's own code.** Prompts are rendered by the engine from the definitions production runs, answers are validated by the product's own schemas, and only the thing under test (a model, a prompt, a parameter) is swapped. Nothing is copied into the lab and edited there.
- **Freezes its inputs.** Whatever the product would fetch (a source shelf, PubMed papers, queries) is fetched once with the product's code and saved with a hash, so every arm reads byte-identical inputs.
- **Pre-registers.** The lab's README states the question, the hypotheses, the metrics and the decision rule before any paid run; `compare` applies the rule mechanically.
- **Uses known answers where they exist** and blind sheets for people where they do not; when the reference is the strongest model rather than a person, it says so.
- **Keeps paid and free steps apart:** `check` and `snapshot` (no model), `run` (paid, resumable, one trial appended per line as it finishes), `score`, `compare` and `sheet` (free, re-runnable on the saved answers).
- **Records provenance** in each run folder: models, parameters, input hashes, hashes of the product files that decide what is measured, the git commit and whether the checkout was dirty.
- **Treats errors as results.** A failed call, a schema failure, a truncation or a refusal is a failed trial, never a pass.
- **Caps spend.** Paid calls go through a ledger that refuses a call which could cross the lab's budget.

## How to run one

From the repository root, with the product's requirements installed (a lab lists any extra dependency in its README) and the product's `.env`:

```sh
python -m scripts.labs.<lab>.lab --env-file /path/to/.env check
python -m scripts.labs.<lab>.lab --env-file /path/to/.env run ...
```

Each lab's README has the exact commands, in order, including a one-repeat pilot to measure cost before the full run.

## Where results go

Into the lab's own `results/` folder, and frozen inputs into its `data/snapshots/`; both are git-ignored by the lab's `.gitignore`. Only code, cases, the README and the decisions below are tracked. A report for people goes to the docs repository and links back here.

## Adding a lab

1. Create `scripts/labs/<name>/` with an `__init__.py`, a `.gitignore` (`results/`, `data/snapshots/`), a `cases/` folder for known answers, and a `README.md` that pre-registers the question, hypotheses, metrics, decision rule and budget before any paid call.
2. Reuse the product's code paths; if the product lacks an adapter the lab needs, add the thinnest one inside the lab, not in the product.
3. Provide `check`, `run`, `score` and `compare` as separate commands, and hermetic tests (stub model, no network) under `backend/tests/` so CI runs them.
4. Add a row to the table below.

## Labs

| Lab | Question | Status |
|---|---|---|
| [`model_choice_fd/`](model_choice_fd/README.md) | Which Claude model for which GeneGuidelines task, measured on fibrous dysplasia | Run 2026-11-20/21, 11.63 USD; synthesis waits for Dorota's blind review, the PubMed decision for the 30-paper check |
| [`guideline_points/`](guideline_points/README.md) | Can a generator→verifier loop write the "What the guideline says about diagnosis" block for every catalog disease, as well as the hand-written FD block? | Runs 2026-11-23 (6.54 USD) and 2026-11-24 (6.60 USD): 6 of 7 diseases get a block; verifier calibrated on FD; the second run adds coverage (MAS now has its endocrine work-up), GeneReviews from NCBI's archive and verifier fixes applied directly; FD's generated block still misses three hand-written points |

## Key decisions

What each lab's pre-registered rule recommends. A row is a recommendation until Darek accepts it and the product changes.

| Task | Model | Evidence | Rationale |
|---|---|---|---|
| Disease wider search (generator + judge) | Haiku 5.5 generator + Sonnet 5.5 judge | `model_choice_fd`, 30 queries x 3, 2026-11-21 | Cheapest arm within the pre-registered bar: pass 0.93, 1 wrong answer, 0 forbidden; Gemma alone today: 0.84 and 11 wrong. Sonnet+Sonnet is best (0.97, 0 wrong) at 0.02 USD per query. |
| Guideline synthesis (5 sections) | Sonnet 5.5, provisional | `model_choice_fd`, FD, 3 documents per arm | Same bar as Opus on every automated metric at 47 % of the cost (1.16 against 2.46 USD per disease); the metrics are at their ceiling, so Dorota's blind review decides. |
| PubMed evidence pass (`pass1-*`) | Opus 5.5, provisional | `model_choice_fd`, FD diagnostics, n = 3 | Only arm meeting the rule: Sonnet matches Opus's paper selection but carries far fewer decision-changing findings; reference is Opus itself until the 30-paper relevance check. Drafting (`pm-4-*`) not decided: its prompt never sees the evidence (product defect). |
