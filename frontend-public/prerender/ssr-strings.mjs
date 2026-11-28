/**
 * The labels the backend needs to server-render a page (backend/seo/), taken from the locale catalogues the app itself reads.
 *
 * The Docker image ships only `dist/` (Dockerfile.backend copies frontend-public/dist to /app/static), not `src/locales`, so build.mjs writes this map to `dist/_ssr-strings.json`. One source of truth: a label changed in a catalogue changes in the server-rendered page on the next build, and nothing is translated twice.
 *
 * Each entry is `flatKey: [catalogue, dotted.path]`. The `ssr.*` block in seo.json holds the few strings no view needed before.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const SSR_LOCALES = ["en", "pl"];

const SOURCES = {
  siteTitle: ["seo", "siteTitle"],
  siteDescription: ["seo", "siteDescription"],
  titleSuffix: ["seo", "titleSuffix"],
  linkGuidelines: ["seo", "linkGuidelines"],
  linkDiseases: ["seo", "linkDiseases"],
  linkAllDoctors: ["seo", "linkAllDoctors"],
  linkAbout: ["seo", "linkAbout"],
  footerDesc: ["common", "footer.desc"],
  notListed: ["disease", "notListedBadge"],
  factGene: ["disease-map", "factGene"],
  factOmim: ["disease-map", "factOmim"],
  factInheritance: ["disease-map", "factInheritance"],
  factPrevalence: ["disease-map", "factPrevalence"],
  diseasesTitle: ["disease-index", "title"],
  guidelinesTitle: ["guidelines", "titleWhatGuidelinesSay"],
  versionNoGuideline: ["guidelines", "versionNoGuideline"],
  noGuidelineTitle: ["guidelines", "gateNoSourcesTitle"],
  noGuidelineBody: ["guidelines", "gateNoSourcesBody"],
  sectionNoSourceNote: ["guidelines", "sectionNoSourceNote"],
  clinicalSummaryHeading: ["guidelines", "clinicalSummaryToggle"],
  clinicalSummaryNote: ["guidelines", "clinicalSummaryNote"],
  shelfTitle: ["guidelines", "sourceShelfTitleParent"],
  basedOn: ["guidelines", "basedOnLabel"],
  pmidLabel: ["guidelines", "pmidLabel"],
  doctorsTitle: ["doctors-page", "title"],
  doctorsLead: ["doctors-page", "lead"],
  doctorsProvenance: ["doctors-page", "provenance.lead"],
  doctorDiseases: ["doctor-profile", "diseases.title"],
  trialsTitle: ["trials", "title"],
  trialsLead: ["trials", "lead"],
  trialsProvenance: ["trials", "provenance"],
  trialsRegistryLink: ["trials", "openOnClinicalTrials"],
  trialsStatus: ["trials", "filterStatusLabel"],
  trialsPhase: ["trials", "filterPhaseLabel"],
};

function load(locale, catalogue) {
  const path = fileURLToPath(
    new URL(`../src/locales/${locale}/${catalogue}.json`, import.meta.url),
  );
  return JSON.parse(readFileSync(path, "utf8"));
}

function pick(object, dotted) {
  return dotted.split(".").reduce((node, key) => (node == null ? undefined : node[key]), object);
}

/** `{ en: { flatKey: label }, pl: { … } }`; throws when a catalogue lost a key, so the build fails instead of the page. */
export function buildSsrStrings() {
  const out = {};
  for (const locale of SSR_LOCALES) {
    const cache = {};
    const labels = {};
    for (const [flatKey, [catalogue, dotted]] of Object.entries(SOURCES)) {
      cache[catalogue] ??= load(locale, catalogue);
      const value = pick(cache[catalogue], dotted);
      if (typeof value !== "string" || value.trim() === "") {
        throw new Error(`ssr-strings: ${locale}/${catalogue}.json has no "${dotted}"`);
      }
      labels[flatKey] = value;
    }
    const ssr = (cache.seo ??= load(locale, "seo")).ssr ?? {};
    for (const [key, value] of Object.entries(ssr)) {
      labels[key] = value;
    }
    out[locale] = labels;
  }
  return out;
}
