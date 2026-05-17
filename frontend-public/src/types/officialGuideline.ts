export type OfficialGuidelineSource = "reviewer" | "workflow" | "seed";

export interface OfficialGuideline {
  readonly diseaseSlug: string;
  readonly title: string;
  readonly authors: string;
  readonly year: number;
  readonly journal: string;
  readonly pmid: string;
  readonly url: string;
  readonly summary: string;
  readonly confirmedBy: string;
  readonly confirmedAt: string;
  readonly source: OfficialGuidelineSource;
}
