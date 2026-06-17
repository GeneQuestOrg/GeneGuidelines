import type { AnalyzedPaper, AnalyzedPaperAccess, AnalyzedPaperVerdict } from "../types/analyzedPaper";

export const BIB_VERDICT_ORDER: readonly AnalyzedPaperVerdict[] = [
  "shelf",
  "suggestion",
  "rejected",
  "low",
] as const;

export const BIB_VERDICT_META: Record<
  AnalyzedPaperVerdict,
  { label: string; short: string; hint: string }
> = {
  shelf: {
    label: "On the source shelf",
    short: "Shelf",
    hint: "selected as a source the synthesis is built on",
  },
  suggestion: {
    label: "Became an AI suggestion",
    short: "Suggestion",
    hint: "produced a delta for clinician review",
  },
  rejected: {
    label: "Considered, set aside",
    short: "Rejected",
    hint: "read and consciously rejected — with a reason",
  },
  low: {
    label: "Low triage signal",
    short: "Low",
    hint: "passed relevance but too weak to act on this run",
  },
};

export const BIB_ACCESS_META: Record<
  AnalyzedPaperAccess,
  { label: string; short: string }
> = {
  oa: { label: "Open access · full text", short: "Open access" },
  abstract: { label: "Abstract only", short: "Abstract" },
  paywall: { label: "Behind paywall", short: "Paywall" },
  unknown: { label: "Access unknown", short: "Unknown" },
};

export function bibliographySourceUrl(paper: AnalyzedPaper): string | null {
  if (paper.pmid) {
    return `https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`;
  }
  if (paper.bookshelf) {
    return `https://www.ncbi.nlm.nih.gov/books/${paper.bookshelf}/`;
  }
  return null;
}

export function bibliographyRefLabel(paper: AnalyzedPaper): string {
  if (paper.bookshelf) {
    return `Bookshelf ${paper.bookshelf}`;
  }
  if (paper.pmid) {
    return `PMID ${paper.pmid}`;
  }
  return paper.ref;
}

export function changeProbabilityPercent(prob: number | null | undefined): number | null {
  if (typeof prob !== "number" || Number.isNaN(prob)) {
    return null;
  }
  return Math.round(Math.max(0, Math.min(1, prob)) * 100);
}

export function groupBibliographyByVerdict(
  papers: readonly AnalyzedPaper[],
  filter: AnalyzedPaperVerdict | "all",
): { verdict: AnalyzedPaperVerdict; items: AnalyzedPaper[] }[] {
  const visible =
    filter === "all" ? [...papers] : papers.filter((p) => p.verdict === filter);
  return BIB_VERDICT_ORDER.map((verdict) => ({
    verdict,
    items: visible.filter((p) => p.verdict === verdict),
  })).filter((g) => g.items.length > 0);
}

export function bibliographyCounts(papers: readonly AnalyzedPaper[]): Record<string, number> {
  const counts: Record<string, number> = { all: papers.length };
  for (const v of BIB_VERDICT_ORDER) {
    counts[v] = papers.filter((p) => p.verdict === v).length;
  }
  return counts;
}
