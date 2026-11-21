import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildPages, LOCALES, ORIGIN } from "./pages.mjs";

const privacyCatalogue = (locale) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../src/locales/${locale}/privacy.json`, import.meta.url)),
      "utf8",
    ),
  );

/** Visible text of an HTML fragment, whitespace collapsed — what a reader without JavaScript reads. */
const textOf = (html) =>
  html
    .replace(/<[^>]+>/g, "")
    .replaceAll("&quot;", '"')
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&")
    .replace(/\s+/g, " ");

/** The catalogue string as it reads once its markup (**bold**, `code`) is applied. */
const plain = (text) => text.replaceAll("**", "").replaceAll("`", "");

/**
 * The failure this guards against is the one that was live until now: a page that
 * returns a title and nothing else. A static page that renders empty is the same
 * bug with more machinery, so every page is held to carrying its own head and a
 * body with the content that makes it worth indexing.
 */
const pages = buildPages();
const byPath = Object.fromEntries(pages.map((page) => [page.path, page]));

describe("prerendered pages", () => {
  it("covers the home page, the about page, the privacy policy and every FD route in both languages", () => {
    expect(pages.map((page) => page.path).sort()).toEqual([
      "/",
      "/about",
      "/diseases/fd",
      "/diseases/fd/map",
      "/diseases/fd/tests",
      "/pl",
      "/pl/about",
      "/pl/diseases/fd",
      "/pl/diseases/fd/map",
      "/pl/diseases/fd/tests",
      "/pl/privacy",
      "/privacy",
    ]);
  });

  it.each([
    ["/pl/privacy", "pl", "21 listopada 2026", "/privacy"],
    ["/privacy", "en", "21 November 2026", "/pl/privacy"],
  ])("%s carries the whole policy, dated, without JavaScript", (path, locale, date, otherPath) => {
    const page = byPath[path];
    const { policy } = privacyCatalogue(locale);
    const text = textOf(page.body);

    expect(page.body).toContain(`<h1>${policy.title}</h1>`);
    // The date comes from one constant; the draft's placeholder never reaches a reader.
    expect(page.body).toContain(`<time datetime="2026-11-21">${date}</time>`);
    expect(text).not.toMatch(/\[data publikacji\]|\[publication date\]|\{\{date\}\}/);
    expect(page.body).toContain(`href="${otherPath}"`);

    // Every heading and every sentence of the catalogue is on the page, in order of sections.
    expect(policy.sections).toHaveLength(10);
    for (const section of policy.sections) {
      expect(page.body).toContain(`<section id="${section.id}">`);
      expect(page.body).toContain(`<h2>${section.heading}</h2>`);
      for (const block of section.blocks) {
        for (const line of block.p !== undefined ? [block.p] : (block.ol ?? block.ul)) {
          expect(text).toContain(plain(line));
        }
      }
    }

    expect(page.body).toContain('<a href="mailto:kontakt@genequest.org">kontakt@genequest.org</a>');
    expect(page.body).toContain("<code>gg.locale</code>");
    expect(page.body).toContain("<code>gg-sub-ref-…</code>");
    // A page about the site, not about a disease.
    expect(page.jsonLd.about).toBeUndefined();
    expect(page.jsonLd.citation).toBeUndefined();
  });

  it("gives both language versions the same sections, so a #section link works in either", () => {
    const ids = (locale) => privacyCatalogue(locale).policy.sections.map((section) => section.id);
    expect(ids("en")).toEqual(ids("pl"));
    expect(ids("pl")).toContain("clinicians");
  });

  it.each(["/", "/pl"])("%s says what the site is and that nobody signs it off", (path) => {
    const page = byPath[path];
    expect(page.title).not.toContain(" · GeneGuidelines");
    expect(page.body).toContain("<h1>");
    expect(page.body.toLowerCase()).toMatch(/no one formally signs off|nikt się pod nim oficjalnie nie podpisuje/);
    // The home page is about the site, not about FD.
    expect(page.jsonLd.about).toBeUndefined();
  });

  it.each(["/about", "/pl/about"])("%s leaves out the switched-off case-context panel", (path) => {
    const body = byPath[path].body;
    expect(body).toContain("<h1>");
    expect(body).not.toContain("SHA-256");
    expect(body.toLowerCase()).not.toContain("discharge summary");
  });

  it.each(pages.map((page) => [page.path]))("%s carries a head a crawler can use", (path) => {
    const page = byPath[path];
    expect(page.title.length).toBeGreaterThan(10);
    expect(page.description.length).toBeGreaterThan(50);
    expect(page.url).toBe(`${ORIGIN}${path}`);
    expect(page.alternates.map((alt) => alt.hreflang).sort()).toEqual([...LOCALES].sort());
    expect(page.jsonLd["@type"]).toBe("MedicalWebPage");
  });

  it.each(pages.map((page) => [page.path]))("%s carries a body, not just a title", (path) => {
    const page = byPath[path];
    // 68 characters is what the live page returned before this existed.
    expect(page.body.length).toBeGreaterThan(400);
    expect(page.body).toContain("<h1>");
  });

  it.each(["/diseases/fd/map", "/pl/diseases/fd/map"])(
    "%s carries every question with the sentence behind it",
    (path) => {
      const body = byPath[path].body;
      expect((body.match(/<blockquote>/g) ?? []).length).toBe(6);
      expect(body).toContain("complete staging evaluation");
      expect(body).toContain("31196103");
    },
  );

  it.each(["/diseases/fd/tests", "/pl/diseases/fd/tests"])(
    "%s carries every row of the sheet and says nobody signed it off",
    (path) => {
      const body = byPath[path].body;
      expect((body.match(/<li>/g) ?? []).length).toBe(14);
      expect(body).toContain("31196103");
      expect(body.toLowerCase()).toMatch(/nie przeglądali|have not reviewed/);
    },
  );

  it.each([
    ["/diseases/fd", "/diseases/fd/guidelines"],
    ["/pl/diseases/fd", "/pl/diseases/fd/guidelines"],
  ])(
    "%s carries the parent view in the app's order: map, list of tests, summary link, contact",
    (path, guidelinesHref) => {
      const body = byPath[path].body;
      const at = (needle) => {
        const index = body.indexOf(needle);
        expect(index, needle).toBeGreaterThan(-1);
        return index;
      };
      const questions = at("complete staging evaluation");
      const tests = at('<ul class="ggp-rows">');
      const summary = at(`href="${guidelinesHref}"`);
      const contact = at('href="mailto:kontakt@genequest.org"');
      expect(questions).toBeLessThan(tests);
      expect(tests).toBeLessThan(summary);
      expect(summary).toBeLessThan(contact);
      expect(body).toContain("31196103");
      expect(body.toLowerCase()).toMatch(/nie przeglądali|have not reviewed/);
      expect(body.toLowerCase()).toMatch(/nie stawiamy diagnoz|we don't diagnose/);
    },
  );

  it("leaves the guideline page to the server, which has the synthesis", () => {
    // The build has no database; backend/seo renders /diseases/fd/guidelines from the real synthesis.
    expect(byPath["/diseases/fd/guidelines"]).toBeUndefined();
    expect(byPath["/pl/diseases/fd/guidelines"]).toBeUndefined();
  });

  it("keeps the withdrawn phrasings out of every page", () => {
    const all = pages.map((page) => `${page.title} ${page.description} ${page.body}`)
      .join(" ")
      .toLowerCase();
    for (const phrase of [
      "kiedy szukać drugiej opinii",
      "sygnały ostrzegawcze",
      "second opinion",
      "red flag",
    ]) {
      expect(all).not.toContain(phrase);
    }
  });
});
