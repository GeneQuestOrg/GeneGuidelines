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
}

export type AudienceCopy = {
  home: HomeCopy;
  disease: DiseaseCopy;
};

export type CopyForView = Record<AudienceView, AudienceCopy>;
