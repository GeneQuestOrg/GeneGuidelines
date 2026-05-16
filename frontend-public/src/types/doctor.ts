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

export interface DoctorEvidence {
  readonly firstOrLastAuthorPapers: number;
  readonly reviewPapers: number;
  readonly citesRecentGuidelines: boolean;
  readonly activeLast2y: boolean;
  readonly guidelineOrConsensusCoauthor: boolean;
}

export interface DoctorPublication {
  readonly pmid: string;
  readonly title: string;
  readonly year: number | null;
  readonly journal: string;
  readonly position: string;
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
}

export interface DiseaseDoctorsPayload {
  readonly diseaseSlug: string;
  readonly source: DoctorListSource;
  readonly doctors: readonly PublicDoctor[];
}
