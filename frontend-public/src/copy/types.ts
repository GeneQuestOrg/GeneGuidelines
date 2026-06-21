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
 * Parent-only IA copy (draft12 parent hub sections).
 * Optional on DiseaseCopy so the clinician audience need not define it.
 */
export interface ParentOrientationCopy {
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
  /** Parent hero — private case upload (draft12). */
  myCaseCta: string;
  /** Parent/clinician hero — disease alert subscription (draft12). */
  notifyCta: string;
  notifyPendingCta: string;
  notifySubscribedCta: string;
  /** Parent/clinician hero — synthesis reader entry (draft12). */
  synthesisCta: string;
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
