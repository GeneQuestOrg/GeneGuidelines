/**
 * The AI synthesis over a disease's source shelf — ONE object per disease,
 * rendered at two depths: a condensed parent/GP projection and the full
 * clinician text. Mirrors the draft10 `GUIDELINES` shape (chat 019, wizja
 * 04-silnik-wiedzy "synthesis over the shelf").
 *
 * Two safety rules baked into the model:
 *   - No reviewer names. The synthesis carries NO `statusBy` / per-paragraph
 *     "verified by Dr. X" attribution — fabricated sign-off was the demo mine
 *     chat 019 told us to defuse. Author names live only in the source
 *     documents we link to.
 *   - Synthesis ≠ suggestions. This is a faithful summary of EXISTING
 *     guidelines. AI deltas beyond the documents (level b) hang alongside as
 *     `suggestions` (GL-3), never merged here.
 */

export type SynthesisStatus = "consensus" | "verified" | "pending" | "superseded";

/** Provenance: which source-shelf document and section a claim comes from. */
export interface ParagraphSource {
  /** Source-shelf document id (e.g. "boyce2019"), or a PMID when not on the shelf. */
  readonly doc: string;
  /** Location within the source document, e.g. "§ Imaging". */
  readonly loc: string;
}

/** Marks where a newer document updates (or supersedes) an older recommendation. */
export interface ParagraphUpdate {
  /** Source-shelf id of the newer document. */
  readonly doc: string;
  /** Source-shelf id of the document this supersedes (drives the "supersedes" marker). */
  readonly supersedes?: string;
  readonly note: string;
}

/**
 * A grounded paraphrase of the passage in a cited abstract that backs one claim
 * (Feature 4, "Where we know this from"). NEVER a verbatim quote — the engine
 * only holds public PubMed abstracts, so we surface a short paraphrase in our
 * own words + PMID attribution. The backend emits these ONLY for claims judged
 * "supported" against the cited abstract, after a deterministic PMID-provenance
 * gate (each `pmid` is guaranteed to be among the paragraph's `citations`).
 */
export interface SourceQuote {
  /** PMID of the cited abstract this paraphrase is drawn from (digits only). */
  readonly pmid: string;
  /** 1–2 short sentences, paraphrased in our own words (never a verbatim copy). */
  readonly paraphrase: string;
  /** Source-shelf docId (optional; for Bookshelf docs without a PMID). */
  readonly doc?: string;
  /** Optional: which aspect of the claim this passage backs. */
  readonly supports?: string;
}

export interface SynthesisParagraph {
  readonly id: string;
  readonly text: string;
  /** Per-claim provenance (clinician view → click through to the source). */
  readonly source?: ParagraphSource;
  /** Cited PMIDs, in citation order. */
  readonly citations?: readonly string[];
  /**
   * Grounded paraphrases of the cited abstract(s) that back this claim
   * (Feature 4; additive, optional). Present only for "supported" claims;
   * absent for "unsupported"/"uncertain" claims and for older syntheses.
   */
  readonly quotes?: readonly SourceQuote[];
  readonly update?: ParagraphUpdate;
  readonly highlight?: boolean;
}

export interface SynthesisSection {
  readonly id: string;
  readonly title: string;
  readonly intro?: string;
  readonly paragraphs: readonly SynthesisParagraph[];
}

/** One actionable "what to do now" step (parent projection). */
export interface WhatToDoStep {
  /** Bold sentence-opener. */
  readonly lead: string;
  readonly body: string;
}

/** "When to seek a second opinion" box (parent projection). */
export interface SynthesisRedFlags {
  readonly title: string;
  readonly items: readonly string[];
}

/**
 * Asymmetric signal on a synthesis section (wizja 03 / chat 019): thumbs-up OR
 * "report a problem" with a note — no bare "not useful" (NFZ contract pressure
 * could suppress a useful-but-inconvenient pointer). The signal is about the
 * QUALITY of the summary (faithful? complete? safe?), not the guideline's validity.
 */
export interface SynthFlagNote {
  /** Never a real name — "Verified reviewer". */
  readonly who: string;
  readonly text: string;
}

export interface SynthSectionSignal {
  readonly up: number;
  readonly flags: number;
  readonly verified: number;
  readonly flagNotes?: readonly SynthFlagNote[];
}

export interface GuidelineSynthesis {
  readonly slug: string;
  readonly kind: "synthesis";
  readonly title: string;
  /** Short label, e.g. "Synthesis · 4 sources". */
  readonly version: string;
  readonly lastUpdated: string;
  /** Source-shelf document ids this synthesis is built from. */
  readonly sourceIds: readonly string[];
  readonly basedOn: string;
  /** First-class "this is an AI summary, not an official guideline" disclaimer. */
  readonly synthDisclaimer: string;
  readonly status: SynthesisStatus;
  /** Actionable steps for the parent projection (data-driven, not hard-coded). */
  readonly whatToDoNow?: readonly WhatToDoStep[];
  /** Second-opinion red flags for the parent projection (data-driven). */
  readonly redFlags?: SynthesisRedFlags;
  /** Whether an interactive decision tree (flowchart) exists for this disease. */
  readonly hasFlowchart?: boolean;
  readonly sections: readonly SynthesisSection[];
}
