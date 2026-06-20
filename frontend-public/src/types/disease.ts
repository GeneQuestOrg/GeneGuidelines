import type { StatusValue } from "@gene-guidelines/ui";

export type DiseaseAccent = "teal" | "amber" | "indigo";

export type DiseaseCoverage = "full" | "skeleton";

export interface Disease {
  slug: string;
  name: string;
  nameShort: string;
  omim: string;
  gene: string;
  inheritance: string;
  summary: string;
  types: readonly string[];
  related: readonly string[];
  prevalenceText: string;
  status: StatusValue;
  statusDate: string | null;
  aiDraftDate: string | null;
  openPRs: number;
  doctorsCount: number;
  trialsCount: number;
  coverage: DiseaseCoverage;
  accent: DiseaseAccent;
  /** Public-catalog visibility (RES-1). Unlisted diseases resolve via direct
   *  link but are hidden from the index until a curator approves them. */
  listed: boolean;
}
