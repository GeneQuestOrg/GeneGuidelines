import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LOCALE, LOCALES, readLocaleFromLocation } from "../router/locale";

import enCommon from "../locales/en/common.json";
import enHome from "../locales/en/home.json";
import enParent from "../locales/en/parent.json";
import enDoctor from "../locales/en/doctor.json";
import enDisease from "../locales/en/disease.json";
import enStartResearch from "../locales/en/start-research.json";
import enTrials from "../locales/en/trials.json";
import enDoctorsPage from "../locales/en/doctors-page.json";
import enGuidelines from "../locales/en/guidelines.json";
import plCommon from "../locales/pl/common.json";
import plHome from "../locales/pl/home.json";
import plParent from "../locales/pl/parent.json";
import plDoctor from "../locales/pl/doctor.json";
import plDisease from "../locales/pl/disease.json";
import plStartResearch from "../locales/pl/start-research.json";
import plTrials from "../locales/pl/trials.json";
import plDoctorsPage from "../locales/pl/doctors-page.json";
import plGuidelines from "../locales/pl/guidelines.json";

/**
 * i18next bootstrap. Design constraints (see plan-i18n-pl-2026-07-16.md):
 *
 *  - **Static bundle, not HTTP lazy-load.** All catalogs are imported and bundled so
 *    a future prerender (SEO2 increment 2) captures fully-translated DOM with no
 *    fetch race / flash of untranslated content.
 *  - **URL is the source of truth for locale.** The initial language is read from the
 *    ``/pl/`` path prefix; unprefixed = English. `AppShell` keeps i18n in sync with the
 *    router on every client navigation. We deliberately do NOT use a language detector
 *    that could fight the URL (one URL = one language keeps SEO clean).
 *  - **English is the default and fallback.**
 */

export const I18N_NAMESPACES = [
  "common",
  "home",
  "parent",
  "doctor",
  "disease",
  "start-research",
  "trials",
  "doctors-page",
  "guidelines",
] as const;

void i18n.use(initReactI18next).init({
  resources: {
    en: {
      common: enCommon,
      home: enHome,
      parent: enParent,
      doctor: enDoctor,
      disease: enDisease,
      "start-research": enStartResearch,
      trials: enTrials,
      "doctors-page": enDoctorsPage,
      guidelines: enGuidelines,
    },
    pl: {
      common: plCommon,
      home: plHome,
      parent: plParent,
      doctor: plDoctor,
      disease: plDisease,
      "start-research": plStartResearch,
      trials: plTrials,
      "doctors-page": plDoctorsPage,
      guidelines: plGuidelines,
    },
  },
  lng: readLocaleFromLocation(),
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: LOCALES,
  ns: I18N_NAMESPACES as unknown as string[],
  defaultNS: "common",
  returnNull: false,
  interpolation: {
    // React already escapes interpolated values, so i18next must not double-escape.
    escapeValue: false,
  },
  react: {
    // Resources are bundled synchronously — no Suspense boundary needed.
    useSuspense: false,
  },
});

export default i18n;
