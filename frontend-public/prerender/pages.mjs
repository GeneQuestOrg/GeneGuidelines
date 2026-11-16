/**
 * What a crawler, a link unfurler and a language model see when they fetch an FD
 * page.
 *
 * Measured 2026-11-15: `https://geneguidelines.genequest.org/pl/diseases/fd`
 * returned 68 characters — the title and nothing else. The content is assembled
 * in the browser from the API, so everything that does not run JavaScript sees an
 * empty document: no index entry, no link preview, nothing for a model to read.
 *
 * This module builds the static version of the FD pages at build time. It is NOT
 * server-side rendering of the React views: the build runs in CI with no backend
 * and no database (see .github/workflows/deploy-azure.yml), so a page is built
 * from the copy that is checked in — the locale catalogues the views themselves
 * read. Anything that only exists in the database (the AI synthesis, the doctor
 * list, the trial list) is named and linked, never invented here.
 *
 * FD only, on purpose. The quotations are about fibrous dysplasia.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (relative) =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");
const loadJson = (relative) => JSON.parse(read(relative));

export const ORIGIN = "https://geneguidelines.genequest.org";
export const LOCALES = ["en", "pl"];

/** English is the canonical, unprefixed URL space; Polish lives under /pl. */
const withLocale = (path, locale) =>
  locale === "en" ? path : `/${locale}${path === "/" ? "" : path}`;

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function catalogues(locale) {
  return {
    seo: loadJson(`../src/locales/${locale}/seo.json`),
    map: loadJson(`../src/locales/${locale}/disease-map.json`),
    tests: loadJson(`../src/locales/${locale}/fd-tests.json`),
    common: loadJson(`../src/locales/${locale}/common.json`),
  };
}

/**
 * The question/sentence pairs and the row order are read out of the views rather
 * than repeated here, so the static page cannot drift from what the app renders.
 */
const askPairs = [
  ...read("../src/views/DiseaseMapView.tsx").matchAll(/\["(askQ\d+)",\s*"(askS\d+)"\]/g),
].map(([, question, sentence]) => [question, sentence]);

const testRowIds = (
  read("../src/views/FdTestsView.tsx").match(/const ROW_IDS = \[([\s\S]*?)\] as const;/)?.[1] ?? ""
)
  .split(",")
  .map((entry) => entry.trim().replace(/^"|"$/g, ""))
  .filter((entry) => entry.length > 0);

const p = (text) => `<p>${esc(text)}</p>`;
const note = (text) => `<p class="ggp-note">${esc(text)}</p>`;

function links(locale, seo, current) {
  const all = [
    ["/diseases/fd", seo.fd.title],
    ["/diseases/fd/map", seo.linkMap],
    ["/diseases/fd/tests", seo.linkTests],
    ["/diseases/fd/guidelines", seo.linkGuidelines],
    ["/doctors?disease=fd", seo.linkDoctors],
  ].filter(([path]) => path !== current);
  return `<nav class="ggp-links">${all
    .map(([path, label]) => `<a href="${esc(withLocale(path, locale))}">${esc(label)}</a>`)
    .join(" · ")}</nav>`;
}

/** /diseases/fd — the hub. Facts and signposts; the live data is named, not faked. */
function fdBody(locale, { seo, common }) {
  return [
    `<h1>${esc(seo.fd.title)}</h1>`,
    p(seo.fd.description),
    `<dl class="ggp-facts">`,
    `<dt>Gene</dt><dd>GNAS</dd>`,
    `<dt>OMIM</dt><dd>174800</dd>`,
    `</dl>`,
    note(`${seo.citation}`),
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd"),
  ].join("\n");
}

/** /diseases/fd/map — the orientation map, questions and all. */
function fdMapBody(locale, { seo, map, common }) {
  const questions = askPairs
    .map(
      ([question, sentence]) =>
        `<li><p class="ggp-q">${esc(map[question])}</p><blockquote>${esc(map[sentence])}</blockquote></li>`,
    )
    .join("\n");
  const steps = [
    map.step1Title,
    map.step2Title.replace("{{name}}", "FD"),
    map.step3TitleExists.replace("{{name}}", "FD"),
    map.step4Title,
    map.step5Title,
  ]
    .map((title) => `<li>${esc(title)}</li>`)
    .join("\n");
  return [
    `<h1>${esc(seo.fdMap.title)}</h1>`,
    p(seo.fdMap.description),
    `<h2>${esc(map.introTitle)}</h2>`,
    `<ol class="ggp-steps">${steps}</ol>`,
    `<h2>${esc(map.askTitle)}</h2>`,
    p(map.askNote),
    `<ul class="ggp-asks">${questions}</ul>`,
    note(map.askSource),
    note(map.safetyBold),
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd/map"),
  ].join("\n");
}

/** /diseases/fd/tests — the printable sheet, as text. */
function fdTestsBody(locale, { seo, tests, common }) {
  const rows = testRowIds
    .map((id) => {
      const row = tests.rows[id];
      const when = row.whenQuote
        ? `<blockquote>${esc(row.whenQuote)}</blockquote>`
        : "";
      return [
        `<li>`,
        `<p class="ggp-q">${esc(row.name)}</p>`,
        `<p>${esc(row.why)}</p>`,
        `<blockquote>${esc(row.quote)}</blockquote>`,
        `<p>${esc(tests.colWhen)}: ${esc(row.when)}</p>`,
        when,
        `</li>`,
      ].join("");
    })
    .join("\n");
  return [
    `<h1>${esc(tests.title)}</h1>`,
    p(seo.fdTests.description),
    p(tests.lede),
    `<ul class="ggp-rows">${rows}</ul>`,
    note(tests.sourceLine),
    note(tests.authorshipLine),
    note(tests.safetyLine),
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd/tests"),
  ].join("\n");
}

/**
 * /diseases/fd/guidelines — the synthesis itself lives in the database and is
 * rebuilt on demand, so it cannot be baked in at build time. What can be baked in
 * is what the page is, which guideline it summarises, and that nobody signs it off.
 */
function fdGuidelinesBody(locale, { seo, common }) {
  return [
    `<h1>${esc(seo.fdGuidelines.title)}</h1>`,
    p(seo.fdGuidelines.description),
    `<p class="ggp-note">${esc(seo.citation)} <a href="https://doi.org/10.1186/s13023-019-1102-9">doi:10.1186/s13023-019-1102-9</a></p>`,
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd/guidelines"),
  ].join("\n");
}

const PAGES = [
  { path: "/diseases/fd", key: "fd", body: fdBody },
  { path: "/diseases/fd/map", key: "fdMap", body: fdMapBody },
  { path: "/diseases/fd/tests", key: "fdTests", body: fdTestsBody },
  { path: "/diseases/fd/guidelines", key: "fdGuidelines", body: fdGuidelinesBody },
];

function jsonLd(locale, page, seo, url) {
  return {
    "@context": "https://schema.org",
    "@type": "MedicalWebPage",
    name: seo[page.key].title,
    url,
    description: seo[page.key].description,
    inLanguage: locale,
    about: {
      "@type": "MedicalCondition",
      name: locale === "pl" ? "Dysplazja włóknista" : "Fibrous dysplasia",
      alternateName: "McCune-Albright syndrome",
      code: { "@type": "MedicalCode", codeValue: "174800", codingSystem: "OMIM" },
    },
    citation: seo.citation,
    audience: { "@type": "MedicalAudience", audienceType: ["Patient", "Clinician"] },
    publisher: {
      "@type": "Organization",
      name: "GeneQuest Foundation",
      url: "https://genequest.org/",
    },
  };
}

/**
 * Every FD page to write, in both languages: where it goes, what its head should
 * say, and the markup a reader without JavaScript gets.
 */
export function buildPages() {
  const out = [];
  for (const locale of LOCALES) {
    const bundle = catalogues(locale);
    const { seo } = bundle;
    for (const page of PAGES) {
      const path = withLocale(page.path, locale);
      const url = `${ORIGIN}${path}`;
      out.push({
        locale,
        path,
        url,
        title: `${seo[page.key].title}${seo.titleSuffix}`,
        description: seo[page.key].description,
        alternates: LOCALES.map((other) => ({
          hreflang: other,
          href: `${ORIGIN}${withLocale(page.path, other)}`,
        })),
        jsonLd: jsonLd(locale, page, seo, url),
        body: page.body(locale, bundle),
      });
    }
  }
  return out;
}
