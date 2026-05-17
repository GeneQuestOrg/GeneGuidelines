import type { CatalogStats, ContentPrSummary, Disease, GuidelineMeta } from "../types";
import type { GuidelinePrDetail } from "../types/contentPr";
import type { DiseaseDoctorsPayload, PublicDoctor } from "../types/doctor";
import type { Foundation } from "../types/foundation";
import type { GuidelineDocument } from "../types/guidelineDocument";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { PrivateContext } from "../types/privateContext";
import type { ResearchRun } from "../types/researchRun";
import type { Therapy } from "../types/therapy";
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

export interface TherapyRepository {
  listForDisease(diseaseSlug: string): Promise<readonly Therapy[]>;
}

export interface FoundationRepository {
  listForDisease(diseaseSlug: string): Promise<readonly Foundation[]>;
}

export interface PrivateContextRepository {
  upload(diseaseSlug: string, file: File): Promise<PrivateContext | null>;
  listForDisease(diseaseSlug: string): Promise<readonly PrivateContext[]>;
}

export interface OfficialGuidelineRepository {
  getForDisease(diseaseSlug: string): Promise<OfficialGuideline | null>;
}
