import type { AudienceView } from "../router/types";

/** A tappable example chip in the "I don't know the diagnosis" card. */
export interface HomeExample {
  label: string;
  hint: string;
}

/** One "Co tu znajdziesz" plain-language point. */
export interface HomeFind {
  title: string;
  body: string;
}

/**
 * Homepage copy — draft13 "Koncepcja A, wersja dopracowana v2". The homepage is a
 * single audience-agnostic design, so both audiences share one `home` namespace.
 * Strings live in `src/locales/{en,pl}/home.json`; `buildHomeCopy` reassembles them
 * into this shape (see ../copy/build.ts).
 */
export interface HomeCopy {
  /* Hero — WARIANT A (default; wariant B/C kept as comments in ./home.ts). */
  eyebrow: string;
  titleLine1: string;
  titleEmphasis: string;
  subtitle: string;

  /* LEFT card — "I know the disease". */
  knowKicker: string;
  knowTitle: string;
  knowDesc: string;
  searchPlaceholder: string;
  searchHint: string;

  /* RIGHT card — "I don't know the diagnosis". */
  dontKicker: string;
  dontBadge: string;
  dontTitle: string;
  dontDescLead: string;
  dontDescEmph: string;
  symptomPlaceholder: string;
  symptomExamples: readonly HomeExample[];
  dontCta: string;

  /* "Co tu znajdziesz" + honest disclosure. */
  findsTitle: string;
  findsSub: string;
  finds: readonly HomeFind[];
  honestFootnote: string;
  honestLinkLabel: string;

  /* "Ostatnio dodane" disease rail. */
  diseasesSectionTitle: string;
  diseasesSectionSub: string;

  /* Emphasised "run research for any disease" tile. */
  newDiseaseEyebrow: string;
  newDiseaseTitle: string;
  newDiseaseSub: string;
  newDiseaseCta: string;

  /* Feedback bar — "add your disease". */
  addTitle: string;
  addSub: string;
  addPlaceholder: string;
  addCta: string;
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
