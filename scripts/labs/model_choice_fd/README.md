# Which Claude model for which task, measured on fibrous dysplasia

Every LLM task in GeneGuidelines moves to a new, separate Anthropic organisation. Which Claude model does each task is decided here on fibrous dysplasia (FD/MAS) data, not on intuition. The design was agreed with Darek on 2026-11-20 (`docs/produkty/geneguidelines/realizacja/plan-porzadki-i-test-fd-2026-11.md`, section "Eksperyment: który model Claude do czego"). Nothing is published to production: the lab reads production only through the public API and keeps every output in the git-ignored `results/`.

**Status 2026-11-21.** All pre-registered arms ran, plus the two judge arms added in the amendment, within budget: 11.63 of 20 USD on the Anthropic ledger, 762 Claude calls, 0 refusals. The decision rules have been applied ([Results](#results)). Synthesis stays provisional until Dorota's blind review; the PubMed decision until the 30-paper relevance check.

## How this experiment works, and where the method comes from

The method follows two existing labs of Darek's. The rules taken from them:

1. **Run the product's own code and swap only the variable under test.** Prompts are rendered by the engine's own helpers from the definitions production runs; outputs are validated by the product's own Pydantic schemas; the wider search runs the product's own pipeline with only the model call swapped. Nothing is copied and edited.
2. **Known-answer cases, written before and independently of any model output.** Where no human gold exists, the strongest model is the reference, and that is said wherever a result rests on it; items that need a human are put on a blind sheet instead of being labelled by us.
3. **Pre-register.** Hypotheses, metrics and the decision rule are written below before any paid run, and `compare` applies the rule mechanically.
4. **Separate commands for separate costs.** `check` and `snapshot` (no model), `run` (paid), `judge-check` and `judge` (paid, small), `score`, `compare` and `sheet` (free, re-runnable on saved answers).
5. **Provenance in every run folder.** `run.json` records models, effort, token policy, repeats, the snapshot hash, the hashes of the product files that decide what is measured, the git commit and whether the checkout was dirty. Each trial is appended to `trials.jsonl` the moment it finishes, with the raw answer, tokens, latency, cost, stop reason and any error; an interrupted run continues where it stopped, and a run folder is never continued with different request code or settings.
6. **Errors are results, never passes.** A failed call, a schema failure, a truncation or a refusal is an error trial. No heuristic fallback is applied inside a trial.
7. **An LLM judge counts only after calibration**: `judge-check` against hand-labelled controls, 95 % or better, the same judge for every compared run.
8. **Repeats and a pilot.** A one-repeat pilot per arm first to measure cost; then the full repeats. A pilot is not a result.
9. **Sequential calls**, so provider contention does not confound latency.
10. **Blind human review**: the sheet shows letters, the key lives in a separate folder.
11. **A summary per experiment** (question, setup, results table with n, findings, decision, follow-ups) and an index of key decisions in `scripts/labs/README.md`.

## Tasks, inputs and what is measured

All inputs were frozen once into `data/snapshots/fd-2026-11-20/` (git-ignored; hashes in its `manifest.json`), so every arm reads byte-identical prompts.

| # | Task | Product code path | Unit of a trial | Shipped today |
|---|---|---|---|---|
| 1 | Synthesis of the five guideline sections from the source shelf | `gs-sec-*` nodes of `backend/flows/specs/guideline_synthesis.json` (synced into `flow_definitions` at every start), shelf from `GuidelineShelfLoadExecutor` | one section; five make a document, assembled by the writer's own logic | `direct:gpt-6-astra` (OpenAI account out of credit since 2026-11-20); baseline = the stored production synthesis of 2026-09-05 |
| 2 | PubMed draft: evidence pass and drafting | `pass1-diagnostics` and `pm-4-diagnostics` of the code-defined pubmed flow (`backend/database.py`, `_ensure_pubmed_flow`), inputs from the real `pm-1` retrieval, `pm-rag` and `pm-2` | one node call | Gemma 4 31B on SiliconFlow |
| 3 | Doctor ranking and role | none: see [Deviations](#deviations-from-the-agreed-design) | – | deterministic code, no model |
| 4 | Disease wider search (generator, then judge) | `identify_disease_wider` in `backend/services/disease_wider_search.py` | one query | Gemma generator; the gpt-5.4 judge fails with 429 (out of credit, probed 2026-11-20), so production runs generator-only |

Inputs:

- **Synthesis**: the 11-document FD shelf from `/api/diseases/fd/source-documents`; the product's shelf loader fetched 7 open-access full texts and 9 abstracts (the two Bookshelf chapters parse to nothing). Each section prompt is about 271,000 characters. Production gives the shelf the direct-model budget, so nothing is trimmed.
- **PubMed**: `pm-1` retrieved 699 FD papers; the evidence pass sees the 80 the product puts in its prompt; the drafting prompt carries the 200-row PMID reference table. The disease block uses the FD prompt profile from `backend/content_seed.json` (production's database row could differ; it is not readable without an admin key).
- **Search**: 30 queries in `cases/search_queries.jsonl`: 7 synonyms and abbreviations, 5 typos, 7 Polish names, 4 symptom descriptions (one in Polish), 4 gene or identifier queries (including `pus3`), 3 that must not resolve (an invented name, an invented eponym, and the FD homonym fibromyalgia). Each case states which answers are accepted, which are forbidden, and whether abstaining is right; three are marked for Darek to confirm.

## Arms and parameters

| Task | Arms | Repeats |
|---|---|---|
| Synthesis | `shipped` (stored, n=1), `gemma`, `sonnet`, `opus` | 3 (Opus may be cut to 2 if the pilot shows the budget needs it; the cut is recorded) |
| PubMed | `gemma`, `haiku`, `sonnet`, `opus` | 3 |
| Search | `gemma` (generator only, as production today), `gemma+haiku`, `gemma+sonnet`, `haiku+haiku`, `haiku+sonnet`, `sonnet+sonnet` (generator+judge) | 3 |

- Model ids: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` through the official `anthropic` SDK (`scripts/labs/model_choice_fd/callers.py`, the only adapter; no product code was changed).
- Output: the product's Pydantic schema as a JSON-schema response format (`output_config.format`), then the product's own validation.
- Thinking: adaptive, the default of all three models (not disabled; Opus 5.5 cannot disable it). Effort is pinned per task and equal for every model in it: synthesis `high`, PubMed `medium`, search `medium`, claim judge `medium`.
- `max_tokens`: the product's rule for reasoning models on its direct path, `max(node max_tokens x 4, 16000)`, so 16,000 for every unit here. Gemma keeps the node's own budget (4,000; 900 for search) and the product's retry policy (up to 5 attempts).
- No server-side `fallbacks`: a `bio` (or other) safety refusal is recorded with its category, not routed around. The product will need its own fallback (another model, or keep the previous version).
- Prompt caching on repeats of synthesis and PubMed units (identical prompts back to back). It changes the bill only; cost per disease is reported uncached, as production would pay it.
- The search arms keep the product's 45-second stage timeout.

## Hypotheses (pre-registered 2026-11-20, before any Claude call)

- **H1 synthesis.** Sonnet 5.5 is within the bar of Opus 5.5 (at most 1.0 fewer key claims on average, at most 0.05 lower anchored-and-valid share) at roughly half the cost; both pass the evidence gate in every document.
- **H2 refusals.** The `bio` classifier does not refuse FD synthesis or PubMed drafting; any refusal is a finding that changes the adapter design.
- **H3 PubMed.** Haiku 5.5 passes the hard gates (no truncated or invalid first attempt, at most 5 % of cited PMIDs outside the prompt) and its evidence-pass selection agrees with Opus at least as well as Opus agrees with itself, minus 0.10.
- **H4 search.** `haiku+haiku` gives no forbidden answer and its pass rate is within 0.05 of `sonnet+sonnet`; the judge keeps p90 latency under the 45-second timeout.

## Amendment of 2026-11-21 (before any Claude call)

Agreed with Darek through the coordinator when the key arrived, before the first Claude call:

- **Order and priority under budget pressure:** (a) the disease-search judge arms first, because production search runs without a judge today and the judge is the first thing that will switch; (b) synthesis Opus against Sonnet; (c) PubMed last.
- **Two more search arms:** `gemma+haiku` and `gemma+sonnet` (today's Gemma generator, a Claude judge). They are eligible under the search rule like the all-Claude arms; a Claude generator is measured too, as it is cheap.
- **PubMed:** the drafting step (`pm-4-diagnostics`) is judged only on JSON validity, truncation and PMIDs outside the prompt; its prose is not scored, because its prompt never receives the evidence pass or the consensus (see Deviations, point 4). Quality is measured on the evidence pass: selection agreement with Opus and the key claims in its findings (the claim judge now reads the `pass1` findings only; the Gemma baseline was re-judged the same way).
- **Task 3** is dropped (no model call), as already described.

## Metrics and decision rules (pre-registered; implemented in `compare.py`)

**Synthesis**, per document (five sections of one repeat, after the writer's duplicate filter):

- evidence gate (ADR 005, `backend/guidelines/evidence.py`): at least one paragraph grounded; and the grounded share;
- anchored-and-valid share: grounded, `source.doc` on the shelf, every citation a shelf PMID, and either a shelf citation or a `source.loc` that names a real heading of that document;
- key FD claims conveyed, judged by the calibrated claim judge over the whole document: the five claims of `backend/scripts/semantic_probe.py` plus "GNAS testing from affected tissue" (verified quote) count; "observe asymptomatic lesions, also in children" is reported separately because its wording has no verified source yet. The judge is Gemma 4 31B (the product's own judge prompt from `semantic_probe.py`): it passed `judge-check` at 100 % of 98 decisions on 2026-11-20, and it is not a Claude candidate, so no candidate grades its own text. Opus may be calibrated and run as a second judge for a cross-check; it does not replace the primary one. Caveat: the controls are short texts, the judged documents are 10,000 to 21,000 characters;
- failed sections, refusals, truncations; full-text documents used; cost per disease (uncached); wall latency (sections run in parallel in production, so the slowest section).

Rule: among Claude arms with the gate passed in every document, no refusal, no failed section and a complete run, the best key-claims mean and the best anchored share set the bar; the cheapest arm within 1.0 claim and 0.05 anchored share wins, **provisionally until Dorota's blind review**, which overrides it.

**PubMed**: hard gates per Claude arm: zero truncated or invalid first attempts and zero refusals in both units; PMIDs cited outside the prompt at most 5 % of all cited. Quality: evidence-pass selection agreement with Opus (mean Jaccard of cited PMID sets) at least Opus's own repeat-to-repeat agreement minus 0.10, and key claims within 1.0 of Opus. The cheapest arm passing wins. The reference is the strongest model, not a human gold set; the 30-citation hand check (blind sheet) decides whether that reference deserves trust.

**Search**: hard gates: no forbidden answer (for example `pus3` resolving to pustular psoriasis), no refusal, p90 latency within 45 s, complete run. Then the best pass rate and the fewest wrong answers set the bar; the cheapest arm within 0.05 pass rate and at most one more wrong answer wins.

Gemma arms are reported as today's baseline; they cannot win, because the decision is which Claude model replaces them.

## Humans in the loop

- **Dorota**: blind synthesis sheet (each section in every version under random letters; ratings for correctness, completeness and usefulness to a parent) and a blind citation check (paragraph next to the source passage it cites). `lab.py sheet --task synthesis`.
- **Darek or Dorota**: 30 papers the evidence passes selected, sampled from all arms, each with its abstract, labelled useful or not for an FD diagnostics section (`lab.py sheet --task pubmed --citations 30`; scored per arm with `sheet-score`). Changed by the amendment from drafted sentences against abstracts, because the drafting prompt never sees the abstracts; that variant is still available as `--task pubmed-citations`.
- **Darek**: confirm the three search cases marked `needs_check`, and the wording of the "observe asymptomatic lesions" claim (with Dorota).

## Budget

Hard cap 20 USD of Anthropic spend for the whole experiment, enforced by `results/ledger.jsonl`: before each call the worst case (prompt at about 3 characters per token, all of `max_tokens` as output) is reserved, and a call that could cross the cap is refused. Planning estimate from the frozen prompts (`lab.py estimate`): synthesis Opus about 4.1 USD and Sonnet about 2.0 USD for 3 repeats; PubMed all three about 1.3 USD; search about 4.9 USD; claim judging by Gemma costs nothing on the Anthropic ledger (an Opus cross-check about 0.5 USD). Total about 12 to 13 USD. Each arm starts with a one-unit, one-repeat pilot to replace these assumptions with measured cost.

## Deviations from the agreed design

1. **Task 3 has no model to choose.** Doctor ranking (`df-5`, `scoring.py`) and role (`df-4`, `role_classifier.py`, ClinicalTrials.gov plus PubMed authorship) are deterministic code, and the clinical-versus-research gate (`backend/doctor_axis.py`) reads NPPES or curated fields. The only model calls in the doctor pipeline are alias generation for PubMed retrieval, the last-resort affiliation-to-country step `df-20` (Brave snippets plus a structured call) and the optional justification `df-7` (off by default). A "50 FD doctors" comparison would measure a feature that does not exist; building an LLM role classifier is a product decision, not a model swap. The public FD directory (33 listed doctors) is snapshotted for the record. Recommendation for those small extraction calls follows task 4's cheapest passing model, unverified.
2. **"pm-4" is not paper selection.** In code, `pm-4-*` nodes draft HTML guideline sections; paper reading and selection happens in `pass1-*`. Both are measured, on the diagnostics section.
3. **`pus3`** must not resolve to pustular psoriasis: that is the product's documented failure the judge was added to stop. The brief said the opposite; the case follows the product.
4. **Two product defects found while rendering the prompts**, reported, not fixed here: seven drafting prompts (`pm-4-overview`, `-epidemiology`, `-pathogenesis`, `-diagnostics`, `-treatment`, `-monitoring`, `-followup`) reference their evidence pass as a whole node, `{{ context.pass1-<section> }}`, which `interpolate_context_placeholders` renders as an empty string; four of them (`overview`, `pathogenesis`, `diagnostics`, `treatment`) also reference `{{ context.pm-rag.result.consensus_context }}`, but the engine stores pm-rag's output without a `result` wrapper, so that is empty too. The drafting model therefore sees only the PMID reference table (titles, with every year printed as `????`) and the disease block, never the evidence pass or the consensus abstracts. The snapshot records both as `evidence_pass_reaches_prompt: false` and `consensus_context_reaches_prompt: false`.
5. **The claim judge is Gemma, not Opus** (decided before any Claude call, after Gemma passed calibration 98/98): it is independent of every Claude candidate. The product's own judge model (gpt-5.5) cannot run.

## Results

2026-11-20 (baselines) and 2026-11-21 (Claude arms). n = 3 repeats per arm unless stated; the shipped synthesis is n = 1. Interpretation in Polish for Darek: `docs/produkty/geneguidelines/realizacja/eksperyment-modele-fd-2026-11.md` in the docs repository. All runs were made from an uncommitted worktree (`git_dirty: true`). Anthropic spend 11.63 USD (synthesis Opus 4.20, Sonnet 1.89; search arms 3.03; PubMed 1.28; claim judging 0.58; pilots 0.64). Refusals by any safety classifier: **0 of 762** Claude calls. Truncations: 0.

**Search** (30 known-answer queries x 3; product's 45 s stage timeout; rule: no forbidden answer and no refusal, then the cheapest arm within 0.05 of the best pass rate and at most one more wrong answer than the fewest):

| Arm (generator + judge) | Pass | Wrong answers | Forbidden | Abstentions | Judged | Latency median / p90 | Cost / query |
|---|---|---|---|---|---|---|---|
| gemma (no judge, production today) | 0.84 | 11 | 0 | 6 | 0 % | 4.1 / 5.3 s | – |
| gemma+haiku | 0.89 | 3 | 0 | 12 | 100 % | 7.6 / 10.3 s | 0.0005 USD |
| gemma+sonnet | 0.91 | **0** | 0 | 14 | 99 % | 8.2 / 11.2 s | 0.0085 USD |
| haiku+haiku | 0.92 | 4 | 0 | 8 | 100 % | 6.5 / 10.3 s | 0.0010 USD |
| **haiku+sonnet** | 0.93 | 1 | 0 | 10 | 100 % | 6.7 / 9.7 s | 0.0081 USD |
| sonnet+sonnet | **0.97** | **0** | 0 | 9 | 100 % | 7.6 / 10.3 s | 0.020 USD |

Rule outcome: **haiku+sonnet**. Every Claude judge removes most of Gemma's confident wrong answers. With Sonnet as judge: 0 wrong answers in gemma+sonnet and sonnet+sonnet, 1 in haiku+sonnet; gemma+sonnet misses the pass bar (0.91 < 0.92) only through more abstentions. Haiku invents: "nunan syndrome" became a separate "Nunan syndrome (KDR)" in 4 of 6 Haiku-judged answers, and the invented "Hurler-Zigglemann syndrome" passes as Hurler syndrome. Claude generators solve the FOP symptom query that Gemma abstains on. No arm recognised "OMIM 174800" (the expected answer awaits Darek's confirmation). Scoring caveat: for `pus3` Gemma gave the right gene but invented disease names and OMIM numbers; the pre-registered rule accepts a gene match, so Gemma's 0.84 is 3 trials too generous.

**Synthesis** (rule: gate passed everywhere, no refusal or failed section, then the cheapest arm within 1.0 key claim and 0.05 anchored share of the best):

| Arm | Docs | Gate | Anchored+valid | Loc found | Paragraphs | Characters | Full-text docs used (of 7) | Key claims (of 6 verified), Gemma judge / Opus judge | Observe-claim | Cost / disease (uncached) | Wall latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| shipped (stored 2026-09-05, most likely gpt-6-astra) | 1 | yes | 1.00 | 1.00 | 25 | 21,210 | 6 | 6 / 6 | yes | – | – |
| gemma | 3 | 3/3 | 1.00 | 0.99 | 24 | 12,162 | 5 | 5 / 5 (always misses histology limits) | 3/3 | – | 42.5 s |
| **sonnet** | 3 | 3/3 | 1.00 | 0.99 | 27.7 | 24,946 | 7 | 6 / 6 | 3/3 | **1.16 USD** | 39.4 s |
| opus | 3 | 3/3 | 1.00 | 1.00 | 27 | 28,318 | 7 | 6 / 6 | 3/3 | 2.46 USD | 55.2 s |

Rule outcome: **Sonnet, provisionally** — it reaches the same bar as Opus at 47 % of the cost and faster. The measurable bar has a ceiling: both Claude models are at the maximum on every automated metric (and so is the shipped text), so these numbers cannot show a difference in clinical quality. That is what Dorota's blind sheet is for (`results/review-synthesis/`, key in `results/review-synthesis-KEY/`): five sections in three versions (shipped, Sonnet, Opus), plus 18 paragraphs beside the source passage they cite. The two calibrated judges (Gemma 98/98, Opus 97/98 on the controls) agreed on every document.

**PubMed** (evidence pass `pass1-diagnostics` on the 80 abstracts; drafting `pm-4-diagnostics` judged on validity and PMIDs only, see the amendment):

| Arm | pass1 valid 1st try | pass1 PMIDs selected | Article numbers instead of PMIDs | Selection vs Opus (Jaccard; Opus vs itself 0.68) | Key claims in pass1 findings (of 6) | pass1 cost / call | pm-4 valid 1st try | pm-4 PMIDs outside the table | pm-4 output tokens | pm-4 cost / call |
|---|---|---|---|---|---|---|---|---|---|---|
| gemma | 3/3 | 14 | 3/3 | 0.25 | 0.67 | – | 3/3 | 1 | 1,237 | – |
| haiku | 3/3 | 24 | 0 | 0.33 | 0.0 | 0.004 USD | 3/3 | 0 | 2,451 | 0.003 USD |
| sonnet | 3/3 | 50 | 1/3 | 0.65 | 0.33 | 0.081 USD | 3/3 | 1 | 5,033 | 0.077 USD |
| **opus** | 3/3 | 46 | 0 | – | 2.67 | 0.172 USD | 3/3 | 0 | 8,873 | 0.230 USD |

Rule outcome: **Opus** for the evidence pass. Haiku fails selection agreement; Sonnet selects the same papers as Opus about as consistently as Opus agrees with itself, but its findings carry far fewer of the decision-changing statements (0.33 against 2.67 key claims). Opus is the reference here, not a person: the 30-paper relevance sheet (`results/review-pubmed-selection/`) is the check on that reference. No truncation anywhere, but only because of the reasoning budget: with the product's raw 4,000-token node budget, Opus's drafting answers (7,211 to 11,046 output tokens with thinking; visible text alone 3,500 to 5,300 tokens) would have been cut, and most synthesis calls too (2,471 to 8,495 output tokens). The drafting prose itself is not compared: its prompt never sees the evidence pass or the consensus.

**Claim judges**: Gemma 4 31B passed `judge-check` 98/98 (primary); Opus 5.5 97/98 (cross-check; missed one claim in a three-claim control).

**Hypotheses**: H1 confirmed (Sonnet within the bar at 47 % of Opus's cost; the bar is at its ceiling, see above). H2 confirmed (0 refusals of 762 calls, `bio` included). H3 rejected (Haiku fails evidence-pass selection agreement and key claims). H4 partly: `haiku+haiku` has no forbidden answer and is within 0.05 of the best pass rate, but its 4 wrong answers put it outside the bar.

## Commands

From the repository root, with the product's `.env` (the Anthropic key is read from that file only):

```sh
pip install -r requirements.txt anthropic   # anthropic is an experiment-only dependency, not a product one
L="python -m scripts.labs.model_choice_fd.lab --env-file /path/to/GeneGuidelines/.env"

$L check --snapshot fd-2026-11-20
$L estimate --snapshot fd-2026-11-20 --task synthesis

# pilots: one unit, one repeat, to measure cost
$L run --task synthesis --arm opus   --snapshot fd-2026-11-20 --repeats 1 --limit-units 1 --out pilot-synthesis-opus
$L run --task pubmed    --arm haiku  --snapshot fd-2026-11-20 --repeats 1 --limit-units 1 --out pilot-pubmed-haiku
$L run --task search    --arm sonnet+sonnet --snapshot fd-2026-11-20 --repeats 1 --limit-units 3 --out pilot-search-sonnet
$L ledger

# the claim judge (Gemma, already calibrated 98/98; re-run if claims or controls change); Opus optional as a cross-check
$L judge-check --judge gemma
$L judge-check --judge opus

# full runs
for a in sonnet opus; do $L run --task synthesis --arm $a --snapshot fd-2026-11-20 --repeats 3 --out fd-synthesis-$a; done
for a in haiku sonnet opus; do $L run --task pubmed --arm $a --snapshot fd-2026-11-20 --repeats 3 --out fd-pubmed-$a; done
for a in gemma+haiku gemma+sonnet haiku+haiku haiku+sonnet sonnet+sonnet; do $L run --task search --arm $a --snapshot fd-2026-11-20 --repeats 3 --out fd-search-${a/+/-}; done

# claims, comparison, sheets (judge, then free)
$L judge --judge gemma --runs fd-synthesis-sonnet fd-synthesis-opus fd-pubmed-haiku fd-pubmed-sonnet fd-pubmed-opus
$L judge --judge opus --runs fd-synthesis-shipped fd-synthesis-gemma fd-synthesis-sonnet fd-synthesis-opus   # cross-check only
J=vllm:google/gemma-4-31B-it
$L compare --judge-label $J --runs fd-synthesis-shipped fd-synthesis-gemma fd-synthesis-sonnet fd-synthesis-opus --out compare-synthesis
$L compare --judge-label $J --runs fd-pubmed-gemma fd-pubmed-haiku fd-pubmed-sonnet fd-pubmed-opus --out compare-pubmed
$L compare --runs fd-search-gemma fd-search-gemma-haiku fd-search-gemma-sonnet fd-search-haiku-haiku fd-search-haiku-sonnet fd-search-sonnet-sonnet --out compare-search
$L sheet --task synthesis --runs fd-synthesis-shipped fd-synthesis-sonnet fd-synthesis-opus --out review-synthesis
$L sheet --task pubmed --runs fd-pubmed-gemma fd-pubmed-haiku fd-pubmed-sonnet fd-pubmed-opus --citations 30 --out review-pubmed-selection

# after a person has filled the sheets
$L sheet-score --sheet review-pubmed-selection   # precision of each arm's evidence-pass selection
```

The commands above are exactly what produced the results in this README (2026-11-20/21). `results/` already holds every run, so `score`, `compare` and `sheet` can be repeated without paying again.

Tests (no network, no model): `pytest -q backend/tests/test_model_choice_fd_lab.py`.

## Files

- `lab.py` the commands; `runs.py` run folders; `compare.py` the decision rules; `sheets.py` blind sheets and the scoring of a filled relevance sheet.
- `callers.py` the Claude adapter, the product-runner caller and the stub; `arms.py` what varies between arms; `pricing.py` prices and the spend ledger; `env.py` key and database isolation.
- `snapshot.py` freezing inputs with the product's code; `task_synthesis.py`, `task_pubmed.py`, `task_search.py` per-task units and scoring; `judge.py` the claim judge and its calibration.
- `cases/` the known-answer search queries, the FD claims and the judge controls.

## Outcome (2026-11-21)

Shipped in [ADR 006](../../../docs/adr/006-claude-only-ai-provider.md):
- **Synthesis:** Sonnet 5.5 at effort high (provisional until the blind clinical sheet is scored).
- **PubMed pass1:** Opus 5.5.
- **Disease search:** Sonnet 5.5 as both generator and judge. This deviates from the pre-registered rule, which picked Haiku generator + Sonnet judge. That arm gave 1 confident wrong answer in 90; Sonnet + Sonnet gave 0 for about 1 cent more per query. The foundation chose zero wrong answers over the cent. The deviation was decided after seeing the results and is recorded here as such.

`pm-4` was not decidable until its `{{ context.pass1-<section> }}` placeholder fix (same ADR); it runs on the Sonnet default until a rerun of this lab with the fix says otherwise.
