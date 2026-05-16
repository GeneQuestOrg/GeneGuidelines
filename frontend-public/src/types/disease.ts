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
  statusBy: string | null;
  statusDate: string | null;
  aiDraftDate: string | null;
  openPRs: number;
  doctorsCount: number;
  trialsCount: number;
  coverage: DiseaseCoverage;
  accent: DiseaseAccent;
}
