/**
 * What a crawler, a link unfurler and a language model see when they fetch the home page, the about page, the privacy policy or an FD page.
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
 * The disease pages are FD only, on purpose: the quotations are about fibrous dysplasia. The home, about and privacy pages are built from their own catalogues, which say nothing disease-specific.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  PRIVACY_POLICY_VERSION,
  VERSION_PLACEHOLDER,
  formatPolicyVersion,
  inlineTokens,
  privacyPolicyHref,
} from "../src/content/privacyPolicy.mjs";

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
    home: loadJson(`../src/locales/${locale}/home.json`),
    about: loadJson(`../src/locales/${locale}/about.json`),
    privacy: loadJson(`../src/locales/${locale}/privacy.json`),
  };
}

/**
 * The question/sentence pairs and the row order are read out of the components rather
 * than repeated here, so the static page cannot drift from what the app renders.
 */
const askPairs = [
  ...read("../src/components/ParentDiseaseMap.tsx").matchAll(/\["(askQ\d+)",\s*"(askS\d+)"\]/g),
].map(([, question, sentence]) => [question, sentence]);

const testRowIds = (
  read("../src/components/FdTestsSheet.tsx").match(/const ROW_IDS = \[([\s\S]*?)\] as const;/)?.[1] ?? ""
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

/**
 * / — the home page. What the site is, what is in it, and the sentence that says nobody signs the summaries off. The disease list and the counts come from the database, so they are linked, not listed.
 */
function homeBody(locale, { seo, home }) {
  const finds = home.finds
    .map((item) => `<li><p class="ggp-q">${esc(item.title)}</p><p>${esc(item.body)}</p></li>`)
    .join("\n");
  const nav = [
    ["/diseases/fd", seo.fd.title],
    ["/diseases", seo.linkDiseases],
    ["/doctors", seo.linkAllDoctors],
    ["/about", seo.linkAbout],
  ]
    .map(([path, label]) => `<a href="${esc(withLocale(path, locale))}">${esc(label)}</a>`)
    .join(" · ");
  return [
    `<p class="ggp-note">${esc(home.eyebrow)}</p>`,
    `<h1>${esc(home.titleLine1)} ${esc(home.titleEmphasis)}</h1>`,
    p(home.subtitle),
    `<h2>${esc(home.findsTitle)}</h2>`,
    p(home.findsSub),
    `<ul class="ggp-rows">${finds}</ul>`,
    note(home.honestFootnote),
    `<nav class="ggp-links">${nav}</nav>`,
  ].join("\n");
}

/**
 * /about — why the site exists. Only the sections every reader sees: the case-context panel and its privacy section are switched off in the app (MY_CASE_ENABLED), so they are left out here as well.
 */
function aboutBody(locale, { seo, about, common }) {
  const h = about.hero;
  const fam = about.specialist.families;
  const cli = about.specialist.clinicians;
  const nots = ["diagnostic", "chatbot", "consultation"]
    .map(
      (key) =>
        `<li><p class="ggp-q">${esc(about.not[`${key}Title`])}</p><p>${esc(about.not[`${key}Body`])}</p></li>`,
    )
    .join("\n");
  const limits = about.limitations.items
    .map((item) => `<li><p class="ggp-q">${esc(item.lead)}</p><p>${esc(item.body.trim())}</p></li>`)
    .join("\n");
  return [
    `<h1>${esc(`${h.leadText1}${h.leadNum}${h.leadText2}`)}</h1>`,
    p(h.leadLine2),
    p(h.leadLine3),
    p(h.tldr),
    `<h2>${esc(about.origins.heading)}</h2>`,
    ...about.origins.paragraphs.map(p),
    `<h2>${esc(about.scale.heading)}</h2>`,
    p(about.scale.closing),
    `<h2>${esc(about.specialist.heading)}</h2>`,
    `<h3>${esc(fam.heading)}</h3>`,
    p(`${fam.p1Lead}${fam.p1Em}${fam.p1Rest}`),
    p(fam.p2),
    p(`${fam.p3Text1}${fam.p3Bold}${fam.p3Text2}`),
    `<h3>${esc(cli.heading)}</h3>`,
    p(cli.p1),
    `<h2>${esc(about.not.heading)}</h2>`,
    `<ul class="ggp-rows">${nots}</ul>`,
    `<h2>${esc(about.limitations.heading)}</h2>`,
    `<ul class="ggp-rows">${limits}</ul>`,
    `<h2>${esc(about.who.heading)}</h2>`,
    p(`${about.who.p1Bold}${about.who.p1Body}`),
    p(about.who.p2),
    note(common.footer.desc),
    links(locale, seo, "/about"),
  ].join("\n");
}

/** One string of the policy as HTML: bold leads, storage key names as code, email addresses as mailto links — the same tokens the React view renders (src/content/privacyPolicy.mjs). */
function policyInline(text) {
  return inlineTokens(text)
    .map((token) => {
      if (token.kind === "bold") return `<b>${esc(token.value)}</b>`;
      if (token.kind === "code") return `<code>${esc(token.value)}</code>`;
      if (token.kind === "email")
        return `<a href="mailto:${esc(token.value)}">${esc(token.value)}</a>`;
      return esc(token.value);
    })
    .join("");
}

function policyBlock(block) {
  if (block.p !== undefined) return `<p>${policyInline(block.p)}</p>`;
  const tag = block.ol !== undefined ? "ol" : "ul";
  const items = (block.ol ?? block.ul).map((item) => `<li>${policyInline(item)}</li>`).join("\n");
  return `<${tag}>${items}</${tag}>`;
}

/**
 * /privacy and /pl/privacy — the whole policy, verbatim from the catalogue the app reads (Polish binding, English a translation), with the publication date filled in from its one constant. Every section keeps its id, so a link to #clinicians lands on the right heading without JavaScript too.
 */
function privacyBody(locale, { privacy }) {
  const { ui, policy } = privacy;
  const other = locale === "pl" ? "en" : "pl";
  const [before, after = ""] = policy.version.split(VERSION_PLACEHOLDER);
  const version = `${policyInline(before)}<time datetime="${PRIVACY_POLICY_VERSION}">${esc(formatPolicyVersion(locale))}</time>${policyInline(after)}`;
  const sections = policy.sections.map((section) =>
    [
      `<section id="${esc(section.id)}">`,
      `<h2>${esc(section.heading)}</h2>`,
      ...section.blocks.map(policyBlock),
      `</section>`,
    ].join("\n"),
  );
  return [
    `<h1>${esc(policy.title)}</h1>`,
    `<p>${version}</p>`,
    `<p class="ggp-note"><a href="${esc(privacyPolicyHref(other))}" hreflang="${other}" lang="${other}">${esc(ui.otherLanguage)}</a></p>`,
    ...sections,
  ].join("\n");
}

/** The orientation map as text: the five steps, then the guideline points, each with its question and the sentence behind it. */
function mapSection(map) {
  const questions = askPairs
    .map(
      ([question, sentence]) =>
        `<li><p>${esc(map[question.replace("askQ", "askP")])}</p><p class="ggp-q">${esc(map[question])}</p><blockquote lang="en">${esc(map[sentence])}</blockquote></li>`,
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
    `<h2>${esc(map.introTitle)}</h2>`,
    `<ol class="ggp-steps">${steps}</ol>`,
    `<h2>${esc(map.askTitle)}</h2>`,
    p(map.askNote),
    `<ul class="ggp-asks">${questions}</ul>`,
    note(map.askSource),
    note(map.safetyBold),
  ];
}

/** The printable sheet's rows as text. */
function testRows(tests) {
  return testRowIds
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
}

/**
 * /diseases/fd — the parent view, in the order the app renders it: the orientation map, the printable list of tests, the AI summary as one link (the summary itself lives in the database), and the address for a case that does not fit.
 */
function fdBody(locale, { seo, map, tests, common }) {
  const contact = "kontakt@genequest.org";
  return [
    `<h1>${esc(seo.fd.title)}</h1>`,
    p(seo.fd.description),
    `<dl class="ggp-facts">`,
    `<dt>${esc(map.factGene)}</dt><dd>GNAS</dd>`,
    `<dt>${esc(map.factOmim)}</dt><dd>174800</dd>`,
    `</dl>`,
    ...mapSection(map),
    `<h2>${esc(tests.title)}</h2>`,
    p(tests.lede),
    `<ul class="ggp-rows">${testRows(tests)}</ul>`,
    note(tests.sourceLine),
    note(tests.authorshipLine),
    `<h2>${esc(map.summaryTitle)}</h2>`,
    p(map.summarySub),
    `<p><a href="${esc(withLocale("/diseases/fd/guidelines", locale))}">${esc(seo.linkGuidelines)}</a></p>`,
    `<h2>${esc(map.unusualTitle)}</h2>`,
    p(map.unusualBody),
    `<p class="ggp-note">${esc(map.unusualNote.replace("{{email}}", contact))}</p>`,
    `<p><a href="mailto:${contact}">${esc(map.unusualCta)} — ${contact}</a></p>`,
    note(seo.citation),
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd"),
  ].join("\n");
}

/** /diseases/fd/map — the orientation map, questions and all (the old address of the map, kept for links already shared). */
function fdMapBody(locale, { seo, map, common }) {
  return [
    `<h1>${esc(seo.fdMap.title)}</h1>`,
    p(seo.fdMap.description),
    ...mapSection(map),
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd/map"),
  ].join("\n");
}

/** /diseases/fd/tests — the printable sheet, as text. */
function fdTestsBody(locale, { seo, tests, common }) {
  return [
    `<h1>${esc(tests.title)}</h1>`,
    p(seo.fdTests.description),
    p(tests.lede),
    `<ul class="ggp-rows">${testRows(tests)}</ul>`,
    note(tests.sourceLine),
    note(tests.authorshipLine),
    note(tests.safetyLine),
    note(common.footer.desc),
    links(locale, seo, "/diseases/fd/tests"),
  ].join("\n");
}

// /diseases/fd/guidelines is not built here: the synthesis lives in the database, and the server renders that page from it at request time (backend/seo), sources and all.

const PAGES = [
  { path: "/", key: "home", body: homeBody, kind: "site" },
  { path: "/about", key: "about", body: aboutBody, kind: "site" },
  { path: "/privacy", key: "privacy", body: privacyBody, kind: "site" },
  { path: "/diseases/fd", key: "fd", body: fdBody },
  { path: "/diseases/fd/map", key: "fdMap", body: fdMapBody },
  { path: "/diseases/fd/tests", key: "fdTests", body: fdTestsBody },
];

function jsonLd(locale, page, seo, url) {
  const base = {
    "@context": "https://schema.org",
    "@type": "MedicalWebPage",
    name: seo[page.key].title,
    url,
    description: seo[page.key].description,
    inLanguage: locale,
    audience: { "@type": "MedicalAudience", audienceType: ["Patient", "Clinician"] },
    publisher: {
      "@type": "Organization",
      name: "GeneQuest Foundation",
      url: "https://genequest.org/",
    },
  };
  // The home, about and privacy pages are about the site, not about a disease: no MedicalCondition, no guideline citation.
  if (page.kind === "site") {
    return base;
  }
  return {
    ...base,
    about: {
      "@type": "MedicalCondition",
      name: locale === "pl" ? "Dysplazja włóknista" : "Fibrous dysplasia",
      alternateName: "McCune-Albright syndrome",
      code: { "@type": "MedicalCode", codeValue: "174800", codingSystem: "OMIM" },
    },
    citation: seo.citation,
  };
}

/**
 * Every prerendered page to write, in both languages: where it goes, what its head should
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
        // The home page carries the site title as it is; every other page gets the suffix, the way the app's own <title> does.
        title: page.key === "home" ? seo.siteTitle : `${seo[page.key].title}${seo.titleSuffix}`,
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
