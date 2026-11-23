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
