/** One paper the knowledge engine considered in a run (read API shape). */

export type AnalyzedPaperVerdict = "shelf" | "suggestion" | "rejected" | "low";
export type AnalyzedPaperStep = "shelf" | "monitor";
export type AnalyzedPaperAccess = "oa" | "abstract" | "paywall" | "unknown";

export interface AnalyzedPaper {
  readonly ref: string;
  readonly step: AnalyzedPaperStep;
  readonly verdict: AnalyzedPaperVerdict;
  readonly reason: string;
  readonly title: string;
  readonly authors: string;
  readonly journal: string;
  readonly year: number | string;
  readonly access: AnalyzedPaperAccess;
  readonly category: string;
  readonly pmid?: string | null;
  readonly bookshelf?: string | null;
  readonly changeProbability?: number | null;
  readonly suggestionId?: string | null;
}
