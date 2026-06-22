/**
 * An AI suggestion hanging ALONGSIDE the synthesis — a delta beyond all the
 * source documents (wizja 04, level b). "Signal, not publication": clinicians
 * leave a 3-state rating + optional comment; nothing is ever merged into the
 * official text. Mirrors the draft10 `SUGGESTIONS` shape.
 *
 *  - kind "addition"      → a new "to consider" item (placement preview)
 *  - kind "modification"  → changes a span → unified diff vs the FULL source doc
 *  - gate "promoted"      → parent sees it as "to discuss with your doctor" (parentText)
 *  - gate "expert"        → clinician-only (real downside if misapplied)
 *
 * Comments carry NO real names (chat 019): "Verified reviewer · led the research".
 */

export type SuggestionKind = "addition" | "modification";
export type SuggestionGate = "promoted" | "expert";
export type EvidenceStrength = "strong" | "moderate" | "low";

export interface SuggestionSignal {
  readonly useful: number;
  readonly not: number;
  readonly wrong: number;
  readonly ratings: number;
  /** How many ratings came from verified specialists (weights the ranking). */
  readonly verified: number;
}

export interface SuggestionComment {
  /** Never a real name — "Verified reviewer". */
  readonly who: string;
  /** Experience tier, e.g. "led the research" / "co-authored research". */
  readonly tier: string;
  readonly text: string;
}

export type DiffLineType = "ctx" | "del" | "add";

export interface DiffLine {
  readonly t: DiffLineType;
  /** Old-file line number (context + deletions). */
  readonly o?: string;
  /** New-file line number (context + additions). */
  readonly n?: string;
  readonly tx: string;
}

export interface SuggestionDiff {
  readonly file: string;
  readonly hunk: string;
  readonly lines: readonly DiffLine[];
}

/** Seed for a regenerated draft — only when a clinician explicitly regenerates. */
export interface RegenSeed {
  readonly version: string;
  readonly basedOn: string;
  readonly note: string;
}

export interface GuidelineSuggestion {
  readonly id: string;
  readonly kind: SuggestionKind;
  /** Section id in the synthesis this hangs beside. */
  readonly targetSection: string;
  /** Human label for that section, e.g. "3. Therapy · denosumab dosing". */
  readonly sectionLabel: string;
  readonly title: string;
  readonly summary: string;
  readonly rationale: string;
  readonly evidence: EvidenceStrength;
  readonly citations: readonly string[];
  readonly gate: SuggestionGate;
  /** Plain-language version for the parent view (only when gate === "promoted"). */
  readonly parentText?: string;
  readonly signal: SuggestionSignal;
  readonly comments: readonly SuggestionComment[];
  /** Unified diff vs the full source document (modifications only). */
  readonly diff?: SuggestionDiff;
  readonly regenSeed?: RegenSeed;
  /**
   * The signed-in clinician's own rating on this suggestion (SIG-1 write loop);
   * null/absent for anonymous viewers or a clinician who has not rated it. Lets
   * the rail restore the selected verdict across reloads.
   */
  readonly myVote?: "useful" | "not" | "wrong" | null;
}

/** Result of casting/clearing a rating: the recomputed aggregate + own verdict. */
export interface SuggestionVoteOutcome {
  readonly signal: SuggestionSignal;
  readonly myVote: "useful" | "not" | "wrong" | null;
}

/**
 * Weighted ranking score (draft10): verified specialist ratings weigh most,
 * "wrong" penalises hardest. Higher = surfaced first in the rail.
 */
export function weightedSuggestionScore(signal: SuggestionSignal): number {
  return signal.useful * 2 + signal.verified * 3 - signal.not - signal.wrong * 4;
}
