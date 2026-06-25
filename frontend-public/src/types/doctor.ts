export type PubmedRole =
  | "research_leader"
  | "research_participant"
  | "case_study_author"
  | "unknown";

export type DoctorListSource =
  | "doctor_finder"
  | "content_seed"
  | "merged"
  | "none";

/** True when list or profile includes Doctor Finder workflow data (including curated merge). */
export function isWorkflowDoctorSource(source: string | undefined): boolean {
  return source === "doctor_finder" || source === "merged";
}

/** Per-disease experience tier — same vocabulary as the global pubmedRole. */
export type DoctorTier = PubmedRole;

export type AddedVia = "pubmed" | "parent" | "consortium" | "nil";

export type RodoStatus = "published_optout" | "informed" | "pending";

export interface DoctorEvidence {
  readonly firstOrLastAuthorPapers: number;
  readonly reviewPapers: number;
  readonly citesRecentGuidelines: boolean;
  readonly activeLast2y: boolean;
  readonly guidelineOrConsensusCoauthor: boolean;
  /** True only when ClinicalTrials.gov links this doctor to a trial for the disease. */
  readonly runsClinicalTrial?: boolean;
  /** Sixth grid signal — how many families recommended this doctor. */
  readonly parentRecCount?: number;
}

/** One place a doctor practises (a doctor may have several). */
export interface Practice {
  readonly type: string;
  readonly name: string;
  readonly address?: string;
  readonly city: string;
  readonly lat: number;
  readonly lng: number;
  readonly website?: string;
}

/** A recommendation left by a parent/carer — a signal PubMed mining cannot surface. */
export interface ParentRec {
  readonly text: string;
  readonly by: string;
  readonly region: string;
  readonly date: string;
}

/** RODO/GDPR provenance for a directory entry (inform-don't-ask-consent, ADR 009). */
export interface Rodo {
  readonly status: RodoStatus;
  readonly emailSent?: string | null;
  readonly note?: string | null;
}

export interface DoctorPublication {
  readonly pmid: string;
  readonly title: string;
  readonly year: number | null;
  readonly journal: string;
  readonly position: string;
  /** Disease is a MAJOR MeSH topic of this paper — it is about the disease. */
  readonly meshMajor?: boolean;
}

export interface PublicDoctor {
  readonly slug: string;
  readonly name: string;
  readonly specialty: string;
  readonly role: string;
  readonly institution: string;
  readonly city: string;
  readonly country: string;
  readonly lat: number;
  readonly lng: number;
  readonly diseases: readonly string[];
  readonly pubmedRole: PubmedRole;
  readonly score: number;
  readonly evidence: DoctorEvidence;
  readonly publications: readonly DoctorPublication[];
  readonly bio: string;
  readonly publicSource: string;
  readonly endorsements: readonly string[];
  readonly contact: string;
  readonly source?: string;
  readonly executionId?: string | null;
  /** How certain we are this profile is one real person (ORCID > name match). */
  readonly identityConfidence?: "high" | "medium" | "low" | null;
  // draft9 directory fields. Optional on the type so fixtures and older API responses stay
  // valid; the backend always returns them (practices has ≥1 entry). Use practicesOf() /
  // tierForDisease() helpers to read with a fallback rather than touching these directly.
  readonly practices?: readonly Practice[];
  readonly experienceByDisease?: Readonly<Record<string, DoctorTier>>;
  readonly addedVia?: AddedVia;
  readonly rodo?: Rodo | null;
  readonly parentRecs?: readonly ParentRec[];
  readonly reviewStatus?: "pending" | null;
}

export interface DiseaseDoctorsPayload {
  readonly diseaseSlug: string;
  readonly source: DoctorListSource;
  readonly doctors: readonly PublicDoctor[];
}

export type ContributionReviewStatus = "pending" | "approved" | "rejected";

export type RecRelation = "parent" | "carer";

/** Body of `POST /api/doctors/submissions` — a parent proposes a missing clinician. */
export interface DoctorSubmissionInput {
  readonly name: string;
  readonly specialty?: string;
  readonly institution?: string;
  readonly city?: string;
  readonly country?: string;
  readonly diseaseSlug?: string;
  readonly note?: string;
}

/** Body of `POST /api/doctors/{slug}/parent-recs` — a parent recommends a doctor. */
export interface ParentRecInput {
  readonly text: string;
  readonly region?: string;
  readonly relation?: RecRelation;
}

/** Response of `POST /api/doctors/submissions` — the submission awaiting moderation. */
export interface DoctorSubmissionResult {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly reviewStatus: ContributionReviewStatus;
  readonly possibleDuplicate: boolean;
}

/** Response of `POST /api/doctors/{slug}/parent-recs` — the rec awaiting moderation. */
export interface ParentRecResult {
  readonly id: string;
  readonly doctorSlug: string;
  readonly reviewStatus: ContributionReviewStatus;
}
