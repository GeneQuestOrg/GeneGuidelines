import { describe, expect, it } from "vitest";
import { buildPages, LOCALES, ORIGIN } from "./pages.mjs";

/**
 * The failure this guards against is the one that was live until now: a page that
 * returns a title and nothing else. A static page that renders empty is the same
 * bug with more machinery, so every page is held to carrying its own head and a
 * body with the content that makes it worth indexing.
 */
const pages = buildPages();
const byPath = Object.fromEntries(pages.map((page) => [page.path, page]));

describe("prerendered pages", () => {
  it("covers the home page, the about page and every FD route in both languages", () => {
    expect(pages.map((page) => page.path).sort()).toEqual([
      "/",
      "/about",
      "/diseases/fd",
      "/diseases/fd/guidelines",
      "/diseases/fd/map",
      "/diseases/fd/tests",
      "/pl",
      "/pl/about",
      "/pl/diseases/fd",
      "/pl/diseases/fd/guidelines",
      "/pl/diseases/fd/map",
      "/pl/diseases/fd/tests",
    ]);
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

  it("never claims the synthesis it cannot bake in", () => {
    // The AI synthesis lives in the database and the build has no database, so
    // the guideline page points at the source instead of inventing a summary.
    for (const path of ["/diseases/fd/guidelines", "/pl/diseases/fd/guidelines"]) {
      expect(byPath[path].body).toContain("10.1186/s13023-019-1102-9");
    }
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
