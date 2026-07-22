import type { AnalyzedPaper, AnalyzedPaperAccess, AnalyzedPaperVerdict } from "../types/analyzedPaper";

export const BIB_VERDICT_ORDER: readonly AnalyzedPaperVerdict[] = [
  "shelf",
  "suggestion",
  "rejected",
  "low",
] as const;

/**
 * `label`/`short`/`hint` are bare i18n keys, not display text — callers must translate them via
 * `t(`common:${meta.label}`)` (or `t(meta.label)` when already scoped to "common").
 */
export const BIB_VERDICT_META: Record<
  AnalyzedPaperVerdict,
  { label: string; short: string; hint: string }
> = {
  shelf: {
    label: "bibliography.verdict.shelf.label",
    short: "bibliography.verdict.shelf.short",
    hint: "bibliography.verdict.shelf.hint",
  },
  suggestion: {
    label: "bibliography.verdict.suggestion.label",
    short: "bibliography.verdict.suggestion.short",
    hint: "bibliography.verdict.suggestion.hint",
  },
  rejected: {
    label: "bibliography.verdict.rejected.label",
    short: "bibliography.verdict.rejected.short",
    hint: "bibliography.verdict.rejected.hint",
  },
  low: {
    label: "bibliography.verdict.low.label",
    short: "bibliography.verdict.low.short",
    hint: "bibliography.verdict.low.hint",
  },
};

/** Same bare-key convention as {@link BIB_VERDICT_META}. */
export const BIB_ACCESS_META: Record<
  AnalyzedPaperAccess,
  { label: string; short: string }
> = {
  oa: { label: "bibliography.access.oa.label", short: "bibliography.access.oa.short" },
  abstract: {
    label: "bibliography.access.abstract.label",
    short: "bibliography.access.abstract.short",
  },
  paywall: {
    label: "bibliography.access.paywall.label",
    short: "bibliography.access.paywall.short",
  },
  unknown: {
    label: "bibliography.access.unknown.label",
    short: "bibliography.access.unknown.short",
  },
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
