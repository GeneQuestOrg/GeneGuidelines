import type { EvidenceStrength, SuggestionSignal } from "./guidelineSuggestion";

/**
 * Level-(c) baseline (wizja 04): a disease with NO agreed guideline. AI assembles
 * a draft FROM SCRATCH, for expert review — explicitly NOT a guideline. The parent
 * never sees this raw (they get the safety gate, GL-2); a clinician/researcher sees
 * the draft here to review/author. Mirrors the draft10 `BASELINE` shape.
 *
 * Content is placeholder until the from-scratch workflow generates it (GL-6 / the
 * engine); experts can later author here, not just review.
 */

/** A step of the from-scratch workflow that produced the draft (build provenance). */
export interface BaselineRunStep {
  readonly label: string;
  readonly meta: string;
  readonly done?: boolean;
  readonly active?: boolean;
}

export interface BaselineItem {
  readonly id: string;
  readonly text: string;
  readonly evidence: EvidenceStrength;
  readonly citations: readonly string[];
  /** Where this item comes from ("consistent across 9 of 11 papers", …). */
  readonly provenance: string;
  readonly signal: SuggestionSignal;
}

export interface BaselineSection {
  readonly id: string;
  readonly title: string;
  readonly items: readonly BaselineItem[];
}

/** Whether a clinician has read the draft yet (shown in the parent gate, GL-2). */
export interface BaselineReadState {
  readonly read: boolean;
  readonly note: string;
}

export interface GuidelineBaseline {
  readonly slug: string;
  readonly title: string;
  readonly builtFrom: string;
  readonly readState: BaselineReadState;
  readonly runSteps: readonly BaselineRunStep[];
  readonly sections: readonly BaselineSection[];
}
