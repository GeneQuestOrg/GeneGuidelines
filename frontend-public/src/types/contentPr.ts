import type { StatusValue } from "@gene-guidelines/ui";
import type { GuidelineParagraph } from "./guidelineDocument";

export type PrReplaceMode =
  | "replace"
  | "insert-after"
  | "already-applied"
  | "modify";

export interface ContentPrSummary {
  readonly id: string;
  readonly disease: string;
  readonly title: string;
  readonly opened: string;
  readonly status: StatusValue;
}

export interface GuidelinePrDiffLine {
  readonly type: "added" | "removed";
  readonly text: string;
}

export interface GuidelinePrPaper {
  readonly pmid: string;
  readonly title: string;
  readonly year: number;
}

export interface GuidelinePrParagraphMap {
  readonly targetSection: string;
  readonly targetParaIds: readonly string[];
  readonly replaceMode: PrReplaceMode;
  readonly insertAfter?: string;
  readonly addedParagraph?: GuidelineParagraph;
}

export interface GuidelinePrDetail extends ContentPrSummary {
  readonly author: string;
  readonly reviewer: string | null;
  readonly summary: string;
  readonly citationsCount: number;
  readonly diff: readonly GuidelinePrDiffLine[];
  readonly papers: readonly GuidelinePrPaper[];
  readonly paragraphMap: GuidelinePrParagraphMap | null;
}
