import { describe, expect, it } from "vitest";
import { buildSsrStrings, SSR_LOCALES } from "./ssr-strings.mjs";

/** The backend renders every page that is not prerendered from these labels; a missing one would surface as an English word on a Polish page, or a blank. */
describe("server-render labels", () => {
  const strings = buildSsrStrings();

  it("has the same keys in every locale", () => {
    const [first, ...rest] = SSR_LOCALES;
    for (const locale of rest) {
      expect(Object.keys(strings[locale]).sort()).toEqual(Object.keys(strings[first]).sort());
    }
  });

  it("never claims a sign-off nobody gives", () => {
    const all = Object.values(strings)
      .flatMap((labels) => Object.values(labels))
      .join(" ")
      .toLowerCase();
    for (const phrase of [
      "physician-reviewed",
      "expert-approved",
      "verified by",
      "zatwierdzone przez",
    ]) {
      expect(all).not.toContain(phrase);
    }
  });

  it("carries the placeholders the backend fills", () => {
    for (const locale of SSR_LOCALES) {
      expect(strings[locale].guidelinesTitle).toContain("{{disease}}");
      expect(strings[locale].doctorsForTitle).toContain("{{disease}}");
      expect(strings[locale].shownOf).toContain("{{total}}");
    }
  });
});
