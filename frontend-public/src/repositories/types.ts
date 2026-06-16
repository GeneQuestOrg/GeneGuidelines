import type {
  InviteCreated,
  InvitePreview,
  MeAccount,
  SelectableRole,
} from "../types/account";
import type { CatalogStats, ContentPrSummary, Disease, GuidelineMeta } from "../types";
import type { GuidelinePrDetail } from "../types/contentPr";
import type {
  DiseaseDoctorsPayload,
  DoctorSubmissionInput,
  DoctorSubmissionResult,
  ParentRecInput,
  ParentRecResult,
  PublicDoctor,
} from "../types/doctor";
import type { Foundation } from "../types/foundation";
import type { GuidelineDocument } from "../types/guidelineDocument";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { PrivateContext } from "../types/privateContext";
import type { SourceDoc } from "../types/sourceDoc";
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
  /** Propose a clinician we are missing (`POST /api/doctors/submissions`). Parent-only. */
  submitDoctor(input: DoctorSubmissionInput): Promise<DoctorSubmissionResult>;
  /** Recommend a doctor (`POST /api/doctors/{slug}/parent-recs`). Parent-only; min 20 chars. */
  submitParentRec(
    doctorSlug: string,
    input: ParentRecInput,
  ): Promise<ParentRecResult>;
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
  /** Curated multi-document source shelf for the disease (GL-1); empty when none. */
  getShelf(diseaseSlug: string): Promise<readonly SourceDoc[]>;
}

export interface AccountRepository {
  /** The authenticated user's account (`GET /api/account/me`). Requires a bearer token. */
  me(): Promise<MeAccount>;
  /** Apply the one-time role selection (`PATCH /api/account/me`). 409 if already set. */
  selectRole(role: SelectableRole): Promise<MeAccount>;
  /** Mint a doctor invite (`POST /api/account/invites`). Parent/superadmin only. */
  createInvite(input?: {
    email?: string;
    doctorSlug?: string;
  }): Promise<InviteCreated>;
  /** Public preview of an invite (`GET /api/account/invites/{token}`). */
  getInvitePreview(token: string): Promise<InvitePreview>;
  /** Redeem an invite (`POST /api/account/invites/{token}/accept`). */
  acceptInvite(token: string): Promise<MeAccount>;
  /** Whether ORCID verification is configured (`GET /api/account/orcid/status`). */
  orcidEnabled(): Promise<boolean>;
  /** ORCID authorize URL to redirect to (`GET /api/account/orcid/login`). */
  orcidLoginUrl(): Promise<string>;
}
