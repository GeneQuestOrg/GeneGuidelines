# ADR 005 — A guideline is published only if it is standing on sources

**Status:** accepted · 2026-09-06

## Context

`severe-growth-deficiency-strabismus-extensive-dermal-melanocytos` sat publicly
listed for a month showing a "synthesis": 1,846 characters across the full
five-section template, dated 2026-08-02, citing nothing. Its sentences read:

> The diagnosis is primarily suggested by the presence of a distinct constellation of
> clinical manifestations…
> There is currently no specific curative therapy for this syndrome.

Both are true. Both are true of almost every genetic syndrome, and neither came from
a source. The disease's entire shelf was two GeneReviews fragments (`NBK601394`,
`NBK621299`) with no readable text, so the model had nothing to write from — and the
template filled anyway, because the prompt asks for five sections and a model asked
for five sections returns five sections.

Nothing failed. The run completed, the page rendered, the disclaimer was present and
accurate. The defect was invisible from every angle except the citation count.

This is the most dangerous output the system can produce. A thin guideline invites a
reader to check the sources. A confident, generic one does not — and the readers here
are parents deciding what to ask a doctor.

## Decision

**A synthesis is served only if at least one paragraph is anchored inside a source** —
carrying either a PMID citation or a position within the document (`source.loc`).
Anything else is withheld, and the disease shows the existing
*no agreed guideline · level (c)* state — the same one a never-synthesised disease
gets, because it says the same true thing: we have nothing sourced to tell you.

Enforced in two places, deliberately:

| Where | What it does | Why both |
|---|---|---|
| `guideline_synthesis_writer_executor` | refuses to store an ungrounded document | stops new padding at the source, and fails the run visibly instead of "succeeding" |
| `GuidelinesService.get_synthesis` | withholds an ungrounded document on read | fixes what is already in the database, with no migration and no waiting for a re-run |

**Attribution is not grounding, and getting this wrong nearly shipped a worse bug.**
The first version of this gate keyed on citations alone. It would have withheld any
honest guideline built from GeneReviews entries, which have no PMID to cite — and a
gate keyed on `source.doc` instead would have passed the padded document unchanged,
because the writer already requires a `source.doc` and padding therefore has one.
The padded document was attributed, in full, to a real shelf entry it never read.

The threshold is one anchored paragraph, not a larger number. Measured on 2026-09-06:
the six real syntheses anchor 25 of 25 paragraphs each, the padded one anchors 0 of 9.
Against a gap that wide a higher bar would be a guess dressed up as rigour. Raise it
only with numbers in hand — `_MIN_GROUNDED_PARAGRAPHS` in
`backend/guidelines/evidence.py`.

The engine still sees withheld rows: the executors read the repository directly, so
fact-checking and monitoring keep working on a disease whose page has gone quiet.

## The standing procedure

When a disease has too little literature to support a guideline:

1. **Do not publish prose.** The gate handles this automatically; do not work around
   it by loosening the prompt or hand-writing a summary.
2. **Leave it on level (c)** — no agreed guideline — which the frontend already
   renders. Do not invent a new "coming soon" state, and do not delist the disease:
   the doctor directory, trials and foundations for it are still worth showing.
3. **Fix the shelf, not the synthesis.** An empty shelf is a retrieval problem. Check
   whether sources exist but are unreadable (Bookshelf entries render no text today —
   that alone accounts for this disease) before concluding the literature is absent.
4. **Re-run when the shelf changes.** If the shelf gains a readable source the next
   synthesis run publishes normally; nothing needs unblocking by hand.
5. **Watch the log line.** `guidelines: withholding ungrounded synthesis for <slug>`
   means a disease has dropped off the guideline layer. That is the intended
   behaviour, but it should never be a surprise.

## Consequences

- One disease loses its page content today. That is the point: it never had content,
  only the appearance of it.
- A future retrieval regression that empties a shelf now degrades to "no guideline"
  instead of silently replacing a good guideline with padding.
- The gate cannot catch a *wrong* claim that carries a citation, nor a paragraph
  anchored in a source that does not support it. It is a floor, not a quality measure; correctness still rests on the source-grounded prompts, the
  clinician signal loop, and the fact that nobody signs these off as official.

## See also

- `backend/guidelines/evidence.py` — the predicate and the measured numbers
- `backend/tests/test_evidence_gate.py` — the failure this prevents, written down
- ADR 008 (product docs) — nobody officially approves a guideline; this ADR is about
  whether one is shown at all, not about who vouches for it
