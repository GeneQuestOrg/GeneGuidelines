import type { StatusValue } from "@gene-guidelines/ui";

export interface DoctorSummary {
  slug: string;
  name: string;
  specialty: string;
  institution: string;
  city: string;
  country: string;
  diseases: readonly string[];
}

export interface TrialSummary {
  nct: string;
  title: string;
  phase: string;
  status: "recruiting" | "active" | "completed" | "withdrawn";
  sponsor: string;
  city: string;
  country: string;
  diseases: readonly string[];
}

export interface ContentPrSummary {
  id: string;
  disease: string;
  title: string;
  opened: string;
  status: StatusValue;
}

export interface GuidelineMeta {
  diseaseSlug: string;
  version: string;
  locale: "en";
  sectionCount: number;
  lastReviewed: string | null;
}

export interface CatalogStats {
  diseaseCount: number;
  doctorCount: number;
  recruitingTrialCount: number;
  openPrCount: number;
}
