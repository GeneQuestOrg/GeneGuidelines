import type { AudienceView } from "../router/types";

export interface HomeCopy {
  eyebrow: string;
  titleLine1: string;
  titleEmphasis: string;
  subtitle: string;
  searchPlaceholder: string;
  aboutLinkLabel: string;
  browseCta: string;
  researchCta: string;
  newDiseaseTitle: string;
  newDiseaseSub: string;
  newDiseaseCta: string;
  diseasesSectionTitle: string;
}

export interface PathwayStep {
  title: string;
  body: string;
}

export interface RedFlag {
  text: string;
}

/**
 * Parent-only IA copy (Phase 3 — draft11 orientation spine + wizja 02).
 * Optional on DiseaseCopy so the clinician audience need not define it; the
 * parent overview renders these sections only when present.
 */
export interface ParentOrientationCopy {
  /** Top-of-hub "Start here — what families wish they'd known" link/banner. */
  startHereLabel: string;
  /** Anchored orientation-framing block the start-here link jumps to. */
  orientationTitle: string;
  orientationBody: string;
  /** Plain-language "what to do now" framing above the pathway. */
  whatToDoNowTitle: string;
  whatToDoNowBody: string;
  /** Copy-paste "Questions for the doctor" block. */
  questionsForDoctorTitle: string;
  questionsForDoctorSub: string;
  questionsForDoctor: readonly string[];
  /** Named "Materials for the family doctor" section (lower-middle). */
  familyDoctorTitle: string;
  familyDoctorSub: string;
  /** Light, persistent "take this to your doctor" affordance. */
  takeToDoctorCta: string;
}

export interface DiseaseCopy {
  personaLabel: string;
  parentPersonaTitle: string;
  parentPersonaSub: string;
  doctorPersonaTitle: string;
  doctorPersonaSub: string;
  skeletonNoticeTitle: string;
  skeletonNoticeBody: string;
  relatedTitle: string;
  tabs: {
    overview: string;
    doctors: string;
    trials: string;
    guidelines: string;
  };
  pathwayTitle: string;
  pathwaySub: string;
  pathwaySteps: readonly PathwayStep[];
  redFlagsTitle: string;
  redFlags: readonly RedFlag[];
  doctorsTitle: string;
  doctorsSub: (count: number) => string;
  doctorsEmpty: string;
  trialsTitle: string;
  trialsSub: (count: number) => string;
  trialsEmpty: string;
  guidelinesTitle: string;
  guidelinesSub: string;
  guidelinesCta: string;
  researchRunCta: string;
  openPrsTitle: string;
  openPrsSub: (count: number) => string;
  officialGuidelineTitle: string;
  officialGuidelineSub: string;
  /** Parent-only orientation spine (Phase 3). Absent for the clinician audience. */
  orientation?: ParentOrientationCopy;
}

export type AudienceCopy = {
  home: HomeCopy;
  disease: DiseaseCopy;
};

export type CopyForView = Record<AudienceView, AudienceCopy>;
