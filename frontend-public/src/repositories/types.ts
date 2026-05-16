import type { CatalogStats, ContentPrSummary, Disease, GuidelineMeta } from "../types";
import type { GuidelinePrDetail } from "../types/contentPr";
import type { DiseaseDoctorsPayload, PublicDoctor } from "../types/doctor";
import type { GuidelineDocument } from "../types/guidelineDocument";
import type { ResearchRun } from "../types/researchRun";
import type { Trial } from "../types/trial";

export interface ContentPrListFilters {
  readonly disease?: string;
  readonly status?: string;
}

export interface DiseaseRepository {
  listDiseases(): Promise<readonly Disease[]>;
  getDiseaseBySlug(slug: string): Promise<Disease | null>;
  searchDiseases(query: string): Promise<readonly Disease[]>;
  getCatalogStats(): Promise<CatalogStats>;
}

export interface GuidelineRepository {
  getGuidelineMeta(diseaseSlug: string): Promise<GuidelineMeta | null>;
  getGuidelineDocument(diseaseSlug: string): Promise<GuidelineDocument | null>;
}

export interface ContentPrRepository {
  listPrs(filters?: ContentPrListFilters): Promise<readonly ContentPrSummary[]>;
  getPrById(prId: string): Promise<GuidelinePrDetail | null>;
}

export interface DoctorRepository {
  listAllDoctors(): Promise<readonly PublicDoctor[]>;
  getDoctorBySlug(slug: string): Promise<PublicDoctor | null>;
  getDoctorsForDisease(diseaseSlug: string): Promise<DiseaseDoctorsPayload>;
}

export interface ResearchRunsRepository {
  listActiveRuns(limit?: number): Promise<readonly ResearchRun[]>;
}

export interface TrialRepository {
  listAll(): Promise<readonly Trial[]>;
  listForDisease(diseaseSlug: string): Promise<readonly Trial[]>;
}
