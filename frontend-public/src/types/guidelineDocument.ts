import type { StatusValue } from "@gene-guidelines/ui";

export type ParagraphChangeType =
  | "consensus"
  | "verified"
  | "pending"
  | "superseded";

export interface ParagraphLastChange {
  readonly type: ParagraphChangeType;
  readonly by: string | null;
  readonly date: string;
  readonly prId?: string;
}

export interface ParagraphPrDiff {
  readonly prId: string;
  readonly removed?: boolean;
  readonly added?: boolean;
}

export interface GuidelineParagraph {
  readonly id: string;
  readonly text: string;
  readonly citations?: readonly string[];
  readonly lastChange?: ParagraphLastChange;
  readonly highlight?: boolean;
  readonly prInDiff?: ParagraphPrDiff;
}

export interface GuidelineSection {
  readonly id: string;
  readonly title: string;
  readonly intro?: string;
  readonly paragraphs: readonly GuidelineParagraph[];
}

export interface GuidelineDocument {
  readonly slug: string;
  readonly title: string;
  readonly version: string;
  readonly lastUpdated: string;
  readonly basedOn: string;
  readonly status: StatusValue;
  readonly statusBy: string | null;
  readonly sections: readonly GuidelineSection[];
}

export interface Citation {
  readonly pmid: string;
  readonly title: string;
  readonly authors: string;
  readonly journal: string;
  readonly year: number;
  readonly type: string;
  readonly isNew?: boolean;
}
