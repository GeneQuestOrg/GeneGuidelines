import type { TFunction } from "i18next";
import type {
  DiseaseCopy,
  HomeCopy,
  HomeFind,
  ParentOrientationCopy,
  PathwayStep,
  RedFlag,
} from "./types";

/**
 * Bridge between i18next catalogs and the audience-keyed copy shapes the views
 * already consume (`HomeCopy` / `DiseaseCopy`). The catalogs are the single source
 * of truth (`src/locales/{en,pl}/*.json`); these builders reassemble them into the
 * existing object shape so call sites stay unchanged. Plural/count strings become
 * i18next plural keys, and array/object copy is read with `returnObjects`.
 *
 * `t` from `useTranslation(ns)` is a `TFunction` bound to a namespace. Without
 * resource type augmentation, i18next types its return as `string`, so array reads
 * are cast through `unknown` to the known shape.
 */

function objectResult<T>(t: TFunction, key: string): T {
  return t(key, { returnObjects: true }) as unknown as T;
}

export function buildHomeCopy(t: TFunction): HomeCopy {
  return {
    eyebrow: t("eyebrow"),
    titleLine1: t("titleLine1"),
    titleEmphasis: t("titleEmphasis"),
    subtitle: t("subtitle"),
    whyLink: t("whyLink"),

    knowKicker: t("knowKicker"),
    knowTitle: t("knowTitle"),
    knowDesc: t("knowDesc"),
    searchPlaceholder: t("searchPlaceholder"),

    dontKicker: t("dontKicker"),
    dontBadge: t("dontBadge"),
    dontTitle: t("dontTitle"),
    dontDescLead: t("dontDescLead"),
    dontDescEmph: t("dontDescEmph"),
    dontSteps: objectResult<string[]>(t, "dontSteps"),
    dontComingSoon: t("dontComingSoon"),

    findsTitle: t("findsTitle"),
    findsSub: t("findsSub"),
    finds: objectResult<HomeFind[]>(t, "finds"),
    honestFootnote: t("honestFootnote"),

    diseasesSectionTitle: t("diseasesSectionTitle"),
    diseasesSectionSub: t("diseasesSectionSub"),

    newDiseaseEyebrow: t("newDiseaseEyebrow"),
    newDiseaseTitle: t("newDiseaseTitle"),
    newDiseaseSub: t("newDiseaseSub"),
    newDiseaseCta: t("newDiseaseCta"),

    addTitle: t("addTitle"),
    addSub: t("addSub"),
    addPlaceholder: t("addPlaceholder"),
    addCta: t("addCta"),
  };
}

function buildOrientation(t: TFunction): ParentOrientationCopy {
  return {
    whatToDoNowTitle: t("orientation.whatToDoNowTitle"),
    whatToDoNowBody: t("orientation.whatToDoNowBody"),
    questionsForDoctorTitle: t("orientation.questionsForDoctorTitle"),
    questionsForDoctorSub: t("orientation.questionsForDoctorSub"),
    questionsForDoctor: objectResult<string[]>(t, "orientation.questionsForDoctor"),
    familyDoctorTitle: t("orientation.familyDoctorTitle"),
    familyDoctorSub: t("orientation.familyDoctorSub"),
    takeToDoctorCta: t("orientation.takeToDoctorCta"),
  };
}

export function buildDiseaseCopy(t: TFunction, includeOrientation: boolean): DiseaseCopy {
  return {
    personaLabel: t("personaLabel"),
    parentPersonaTitle: t("parentPersonaTitle"),
    parentPersonaSub: t("parentPersonaSub"),
    doctorPersonaTitle: t("doctorPersonaTitle"),
    doctorPersonaSub: t("doctorPersonaSub"),
    skeletonNoticeTitle: t("skeletonNoticeTitle"),
    skeletonNoticeBody: t("skeletonNoticeBody"),
    relatedTitle: t("relatedTitle"),
    tabs: {
      overview: t("tabs.overview"),
      doctors: t("tabs.doctors"),
      trials: t("tabs.trials"),
      guidelines: t("tabs.guidelines"),
    },
    pathwayTitle: t("pathwayTitle"),
    pathwaySub: t("pathwaySub"),
    pathwaySteps: objectResult<PathwayStep[]>(t, "pathwaySteps"),
    redFlagsTitle: t("redFlagsTitle"),
    redFlags: objectResult<RedFlag[]>(t, "redFlags"),
    doctorsTitle: t("doctorsTitle"),
    doctorsSub: (count: number) => t("doctorsSub", { count }),
    doctorsEmpty: t("doctorsEmpty"),
    trialsTitle: t("trialsTitle"),
    trialsSub: (count: number) => t("trialsSub", { count }),
    trialsEmpty: t("trialsEmpty"),
    guidelinesTitle: t("guidelinesTitle"),
    guidelinesSub: t("guidelinesSub"),
    guidelinesCta: t("guidelinesCta"),
    myCaseCta: t("myCaseCta"),
    notifyCta: t("notifyCta"),
    notifyPendingCta: t("notifyPendingCta"),
    notifySubscribedCta: t("notifySubscribedCta"),
    synthesisCta: t("synthesisCta"),
    openPrsTitle: t("openPrsTitle"),
    openPrsSub: (count: number) =>
      count === 0 ? t("openPrsSubNone") : t("openPrsSub", { count }),
    officialGuidelineTitle: t("officialGuidelineTitle"),
    officialGuidelineSub: t("officialGuidelineSub"),
    ...(includeOrientation ? { orientation: buildOrientation(t) } : {}),
  };
}
