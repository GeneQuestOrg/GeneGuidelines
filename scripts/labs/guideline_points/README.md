# Guideline points: a generator→verifier loop for "What the guideline says about diagnosis – to show your doctor"

GeneGuidelines content is generated on demand for any rare disease, and its quality has to come from an automatic verifier loop plus a plain "AI-generated, nobody approved it" notice, not from human review (Darek, 2026-11-23). Today the block "What the guideline says about diagnosis – to show your doctor" exists only for FD, hand-written in `frontend-public/src/locales/{en,pl}/disease-map.json` (`askP1-6`, `askQ1-6`, `askS1-6`) and checked twice by an independent verifier against the full guideline. This lab is phase 1: it builds the block for every catalog disease with the product module `backend/guidelines/points/`, measures what the loop catches, and compares FD with the hand-written block. Storing, serving and rendering the block is phase 2. Nothing here writes to a database or to production; production is read only through its public API.

## Question

Can a generator→verifier loop produce, for each catalog disease with a guideline-grade source, 3–6 points in the shape of the hand-written FD block (verbatim English quote, EN/PL summary that says no more and no less, one open question for the doctor in EN/PL) that hold up as well as the hand-written block, within about 25 USD for the whole catalog?

## Design (product code: `backend/guidelines/points/`)

| Step | What | Where |
|---|---|---|
| Inputs | The disease's shelf from the production API; each document graded from bibliographic metadata, not from the shelf's model-written `role`: **A** consensus statement or practice guideline (PubMed publication type, or a title that says guideline/consensus/recommendations/Delphi), **B** GeneReviews chapter (book from Europe PMC), **C** other review (PubMed type Review, StatPearls). Ungraded documents are never used. | `sources.py` |
| Full text | Open-access articles through the product's Europe PMC / NCBI reader (`backend/tools/pmc_fulltext.py`) with citation links stripped from the XML; Bookshelf chapters through `backend/tools/bookshelf_fulltext.py`. A document whose full text cannot be read is not shown to the generator and is reported; nothing is generated from an abstract. Non-English full text is excluded (quotes must be English). | `sources.py`, `snapshot.py` |
| Generator | Claude Sonnet 5.5, effort high, production adapter (ADR 006: Sonnet is the synthesis model; Haiku is excluded from steps that state facts). Reads every readable graded document, strongest grade first, up to 700,000 characters; told to quote the strongest document that says a thing. The documents are a cached prefix, so revision rounds re-read them from the prompt cache. | `prompts.py`, `claude.py` |
| Deterministic check | Every quote must be found verbatim in the full text of the document it names, after normalising typography (quotes, dashes, whitespace, case) and dropping citation markers; "…" pieces must appear in order within one paragraph (or two consecutive paragraphs of one section) on word boundaries. A point that fails is never sent to the verifier and never published. | `quote_check.py` |
| Verifier | Claude Opus 5.5, effort high, a separate call with its own prompt. Reads each quote inside its surrounding paragraphs (plus the exact text left out at any "…") and returns PASS or FIX with exact replacement text and a reason: fair in context, summary faithful (modality, qualifiers, nothing added, EN = PL), question open and not advice, clinically correct Polish, nothing framed as approved. | `prompts.py` |
| Loop | Failed points go back to the generator with the check's or the verifier's feedback, at most 2 revision rounds; still failing = dropped. A PASS that carries a proposed fix counts as FIX; a failed call is a failure, never a pass. Publish only with at least 3 accepted points. Every round is recorded. | `loop.py` |
| Block | Titles per basis (only an all-guideline block is called "the guideline"), and a source note written by code: the documents quoted, and that the summaries and questions are AI-written, machine-checked and approved by nobody. | `block.py` |

## Pre-registered rules (2026-11-23, before any paid call)

1. **Deterministic check calibration** (`check`, free): all six hand-written FD quotes are found verbatim in the frozen FD/MAS consensus (PMID 31196103), and all ten verifier controls pass the check (so they reach the verifier).
2. **Verifier calibration** (`verifier-check`, Opus, 2 repeats): 16 known answers built from the FD block before any verifier call (`cases/verifier_controls.json`): the six hand-written points (expected PASS) and ten copies each broken in one way: modality, an added test, "official" framing, an auditing question, an omission that drops a condition, an advising question, a Polish meaning reversal, a quote cut before its false-negative caveat, a dropped "usually", a presupposing question (expected FIX). Batches never contain two versions of the same point. **Rule:** in every repeat at least 5 of 6 gold points PASS and at least 9 of 10 corruptions FIX. If the rule is not met, the verifier prompt may be revised once, the revision is recorded here, and the check is re-run; the catalog run proceeds either way and the report says whether the verifier was calibrated.
3. **Publication** follows the loop's rule only (at least 3 points through both gates); the lab does not override it by hand.
4. **FD comparison** is descriptive (n = 1 run): each hand-written point is matched to generated points that quote the same passage; found, missed, extra, and weaker or stronger wording are reported. No pass/fail threshold.
5. **Budget:** hard cap 25 USD of Anthropic spend across all commands, enforced by `results/ledger.jsonl` (the worst case of each call is reserved before it is made; a call that could cross the cap is refused and the run stops).

Metrics per disease: shelf documents graded and readable, documents shown to the generator, points drafted, accepted and dropped, revision rounds, whether the block would publish, its basis, cost and tokens.

## Amendment of 2026-11-24 (before the second run)

Darek approved four changes after the first run; the second run measures them, on a new snapshot (`2026-11-24`) whose GeneReviews chapters are read from NCBI's bulk archive with the product's reader (`backend/tools/genereviews_archive.py`), and whose shelves pass the relevance check (`backend/guidelines/relevance.py`).

- **Loop:** a coverage review (Opus, own prompt) after the draft, with the generator adding a point per gap (up to 8 points); a FIX with complete replacements whose quote passes the verbatim check is published as the verifier wrote it; on a revision the verifier sees its previous verdict; titles by basis; quotes from sources without an open licence at most 400 characters; GeneReviews credit on its points.
- **Worked example:** the hand-written FD block is the generator's worked example and the verifier's calibrated PASS example for every disease except FD, where it is held out.
- **Verifier calibration** is re-run with the new verifier prompt and the calibration examples held out (they are the gold), under the same rule as before.
- **Rules for this run** (descriptive, n = 1): the FD comparison as before; MAS passes its new requirement if at least one accepted point is about the endocrine work-up; publication follows the loop's rule only. Budget: up to 25 USD more, enforced by the same ledger (`--cap 32`, the first run having spent 6.54 USD).

## Amendment of 2026-11-25: the bricks pipeline (registered before any paid call)

Darek agreed to replace the one generator and one verifier with small bricks, each a writer (Sonnet 5.5) with its own short checker (Opus 5.5): select, quote, summary_en, question_en, translate_pl, then assembly by code (`backend/guidelines/points/bricks/`, `pipeline.py`; docs plan `docs/produkty/geneguidelines/realizacja/plan-cegielki-punkty-wytycznych-2026-11.md`). No prompt or check sets a number of points, words or sentences. The kept limits: a quote from a document without an open licence at most 400 characters (the point is dropped, never cut); one retry of the items a brick rejects; the run's cost cap.

What is measured (`bricks-calibrate`, `bricks-run`, `bricks-report`; snapshot `2026-11-24`; budget up to 30 USD, enforced by the ledger):

1. **Checker calibration** (`bricks-calibrate`, 2 repeats): each checker sees the six hand-written FD points and the controls of its kind: quote checker `c-truncated`, `c-omission`; summary checker `c-modality`, `c-added`, `c-official`, `c-qualifier`; question checker `c-audit`, `c-advice`, `c-presuppose`; Polish checker `c-polish`. A batch never holds two versions of one point. Code checks come first: a quote with "…" is rejected by code (the bricks quote whole sentences), so hand-written point 3 counts as not passing the quote checker and `c-omission` as caught. **Rule, in every repeat:** each checker passes at least 5 of the 6 hand-written points, and at least 9 of the 10 controls are caught. An effort arm (`--effort medium`) runs the same rule; a checker moves to medium only if it passes.
2. **Runs** (`bricks-run`, 3 repeats each on FD, MAS, FOP, OI). The FD worked example is held out for FD and for MAS (it quotes MAS's guideline).
   - **FD:** a hand-written point is found when the anchor of an accepted point lies inside its quote (after normalisation). **Gate:** at least 5 of 6 found in the final block, in each of the 3 runs. Found at selection is reported too.
   - **Regression points** (`cases/regression_points.json`): FOP avoid biopsy, FOP genetic confirmation, OI family history, OI molecular testing; found when an accepted point quotes the listed paragraph and contains the phrase. MAS: at least one accepted point about the endocrine work-up. **Gate:** each found in at least 2 of 3 runs.
   - **Cost:** per run; the production cap becomes 1.3 times the measured maximum.
3. **Then** a side-by-side on production data (`python -m backend.guidelines.points.cli --dry-run --yes`) for Darek. Nothing changes on the live pages until he approves it.

### Calibration of 2026-11-28 and the one revision it led to (recorded before the re-run)

First calibration (`results/bricks-2026-11-28/calibration.json`, `calibration-medium.json`; 0.69 USD for both arms; ledger cap raised to 43 USD, the earlier labs having spent 13.14 of it): all 10 controls caught in every repeat at both efforts; the question and Polish checkers passed 6 of 6 hand-written points, the quote checker 5 of 6 (point 3 has "…", rejected by code, as registered). **The summary checker passed 4 of 6 at high effort in both repeats (medium: 4 and 5), so the rule was not met.** It rejected point 3 (its summary names GNAS, which the quoted sentences do not: the finding of both earlier labs, and a correct one) and point 6 ("A biopsy is usually needed only…" for "Biopsy with histological evaluation of suspected bone disease is usually only necessary…": it called the shorter subject a dropped limit).

Revision, once, as the rule of 2026-11-23 allows: the summary checker's prompt now says what a qualifier is (a word or clause that says when, how often, for whom or under what condition the statement holds) and that a summary may name the quote's subject more briefly when what is said about it stays the same. Nothing else changes. The whole calibration is re-run at both efforts under the same rule; the runs proceed either way and the report says whether the summary checker was calibrated.

### Pilot run of 2026-11-28 and what it changed (recorded before any registered run)

One pilot run on FD through the API (`results/bricks-2026-11-28/pilot-api-wide-scope-fd.json`, 2.84 USD; not one of the registered runs). The re-run calibration had passed at both efforts after the one revision above (10 of 10 controls caught; quote and summary checkers 5 of 6 hand-written points, question and Polish checkers 6 of 6). The pilot published a clean block with all six hand-written points in it, and **57 points**: 60 selected, 27 of them added by the coverage checker (every organ system's baseline tests, imaging protocols, reference values). The registered FD gate measures recall only, so a block that lists everything passes it; an independent review of the code found the same, and that the MAS topic is met by the bare word "endocrine".

Changed before any registered run:

- **Scope** (`bricks/select.py`): the block is about establishing the diagnosis (how it is made and when it is certain; which test confirms it and what a result can and cannot show; whether a procedure is needed, when it must be avoided, how it must be done; the subtype or extent where a document makes it part of the diagnosis). The work-up after diagnosis does not belong. The selector names the decision a statement changes; the coverage checker removes as readily as it adds. Still no number of points anywhere.
- **Measures** (all recomputable from saved records): next to the registered FD rule, a stricter reading (the point quotes the consensus, its quote holds a whole sentence of the hand-written quote, each hand-written point needs a point of its own); next to the registered MAS rule, a stricter one (an endocrine section, or a quote that names a gland, a hormone or a test); `oi-molecular-testing` also accepts the grade A guideline's statement (21829228 ¶43); points per block are reported (no gate); a run file records the commit and the hashes of the product files.
- **In-sample note:** the prompts name the kinds of statement the earlier FD runs missed (what a negative test cannot rule out, how a sample must be handled), so FD recall is partly in-sample; FOP and OI are the out-of-sample check.
- **A brick with no items makes no call; a refused call in the lab is recorded** instead of ending the process.

**Agent-operated runs.** Darek asked (2026-11-28) for no further API spend on the foundation's key for now. `bricks-agent-step` runs the same pipeline code with Claude Code subagents as the models (Sonnet for the writers, Opus for the checkers; `agent_caller.py`): each call is a request file an agent answers with a JSON file, and the run is replayed to the next unanswered call. It is not the production request (no pinned effort, no response schema enforced by the API, no cache), so it measures what the prompts select and write, not cost. The registered API runs (3 each on FD, MAS, FOP, OI) and the dry run on production data are still to be done with the real adapter before the switch; this session's API spend on the bricks stands at 4.19 USD.

### Agent-operated pilot of 2026-11-28 and the second scope revision (recorded before the runs it applies to)

Under the first narrowed scope the selector chose 21 (FD), 21 (MAS), 10 (FOP) and 31 (OI) locations, and the coverage checker still added more than it removed (FD +5 −2, MAS +9 −1, OI +5 −3, FOP +1 −2). Two causes showed in the lists: one paragraph split into a location for each sentence (six for ¶15 of the FD/MAS consensus), and choices only a laboratory makes (which sequencing method, MLPA on fibroblast DNA, how a report is worded: most of the OI list, from the EMQN laboratory guideline). FOP ran to the end as the test of the agent-operated mode (`results/bricks-2026-11-28/pilot-agent-scope2/`): published, 8 points, both FOP regression points found; the question checker rejected 5 of 9 first drafts and the Polish checker 4 of 8, and all but one passed on the retry.

Revision: a statement belongs only when a parent could ask the doctor about it and the answer could change what is done; a choice between techniques that the laboratory or the specialist makes does not belong; one location for each decision, not for each sentence; the checker removes a statement that serves a decision another one already serves. In code, a point whose quote is part of another point's quote from the same document is dropped (`pipeline._without_contained`). The runs below (`results/bricks-2026-11-28/*-r1.json`, agent-operated) use this version.

## Commands

From the repository root, with the product's requirements installed (Python 3.12, `anthropic==2.12.0`) and the product's `.env` (the Anthropic key is read from that file only):

```sh
python -m scripts.labs.guideline_points.lab --env-file ../GeneGuidelines/.env snapshot --name 2026-11-23
python -m scripts.labs.guideline_points.lab --env-file ../GeneGuidelines/.env check --snapshot 2026-11-23
python -m scripts.labs.guideline_points.lab --env-file ../GeneGuidelines/.env verifier-check --snapshot 2026-11-23 --out <dir>
python -m scripts.labs.guideline_points.lab --env-file ../GeneGuidelines/.env run --snapshot 2026-11-23 --out <dir>
python -m scripts.labs.guideline_points.lab --env-file ../GeneGuidelines/.env report --snapshot 2026-11-23 --out <dir>
```

`--out` may be outside the repository; inside it, use `results/`, which git ignores. `run` is resumable: a disease whose result file exists is skipped, and a folder started with other product code is refused. Tests: `backend/tests/test_guideline_points.py` (deterministic check, grading, loop control and the Claude caller, all with the model mocked).

## Results (2026-11-23, two runs of the whole catalog, 6.54 USD)

Run on commit `814aa36`, snapshot `2026-11-23`; the full report (per disease: documents, block, every FIX) was written by `report` outside the repository and is not tracked.

- **Calibration:** the deterministic check finds all six hand-written FD quotes. The verifier met the rule in both repeats: 10/10 corruptions caught each time; hand-written points 6/6 and 5/6 (the one FIX: summary 3 names GNAS, which the quoted sentences do not).
- **Catalog:** 6 of 7 diseases get a block in both runs (fd 5/6 points, mas 6/5, fop 3/3, noonan 4/5, osteogenesis-imperfecta 5/5, stargardt-disease 5/3); the ultra-rare syndrome gets none, because its two shelf entries are unreadable GeneReviews chapters on other diseases. Noonan and Stargardt rest on reviews only. 60 points drafted, 27 passed on the first round, 55 accepted, 5 dropped; of 97 verifier fixes, 58 were to the questions. 0.35–0.62 USD per disease per run.
- **FD against the hand-written block:** every run reproduces points 1, 2, 3 and 6; run 1 misses the blood-test and tissue-handling points, run 2 misses the blood-test point. The loop checks what the generator chose, never what it left out.
- **Found and fixed after the run** (`97b5bc8`): reviews and case reports graded A by title; PMC list items glued together, which failed a correct FOP quote; the closest-passage hint inside long lists.
- **Not solved:** NCBI Bookshelf serves automated fetches a reCAPTCHA page, so no GeneReviews chapter could be read (the production synthesis uses the same reader); several guidelines are not in PubMed Central; the verifier is inconsistent on compound questions and on some Polish wording across calls.

## Results of the second run (2026-11-24, 6.60 USD)

Snapshot `2026-11-24` (GeneReviews for FD/MAS, FOP and OI read from NCBI's archive; the two off-disease chapters on the PUS3 shelf left out by the relevance check), commit `1ce6a5d`.

- **Calibration** (new verifier prompt, calibration examples held out): rule met in both repeats, 10/10 corruptions caught, hand-written points 5/6; the one FIX, in both repeats, is hand-written point 3 (its summary names GNAS, which the quoted sentences do not; its question "is this test worth considering?" nudges toward a test). 0.63 USD.
- **Catalog:** 6 of 7 diseases publish (fop 8, fd 8, mas 8, noonan 6, osteogenesis-imperfecta 8, stargardt-disease 7 points); the PUS3 syndrome has no readable document about it. The coverage review added 4 points in every disease. Of 47 point verdicts, 29 were PASS, 16 FIX applied as the verifier wrote them (14 of 29 fixes were to the Polish summary), 2 points withdrawn; no disease needed a revision round. 0.74–1.16 USD per disease, 5.97 USD in all.
- **MAS** now covers the endocrine work-up: growth hormone and prolactin, thyroid, and fasting phosphate (no point on precocious puberty).
- **FD against the hand-written block** (worked example held out): points 1, 3 and 6 are reproduced; 2 (a single lesion usually needs histology), 4 (a negative blood test cannot exclude FD) and 5 (tissue handling for GNAS) are not. The coverage review spent its four gaps on the MAS-type evaluation (thyroid, growth hormone, phosphate, craniofacial CT) instead. FD keeps its hand-written block on the page.
- **Gained from GeneReviews:** FOP "biopsies of lesions are never indicated" and "a variant of uncertain significance neither confirms nor rules out"; OI "no family history does not rule out the diagnosis".
