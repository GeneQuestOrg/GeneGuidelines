import { describe, expect, it } from "vitest";
import { splitLocale, withLocalePrefix } from "./locale";

describe("splitLocale", () => {
  it("treats an unprefixed path as English canon", () => {
    expect(splitLocale("/diseases/fd")).toEqual({ locale: "en", pathname: "/diseases/fd" });
    expect(splitLocale("/")).toEqual({ locale: "en", pathname: "/" });
    expect(splitLocale("")).toEqual({ locale: "en", pathname: "/" });
  });

  it("strips a /pl prefix and reports Polish", () => {
    expect(splitLocale("/pl/diseases/fd")).toEqual({ locale: "pl", pathname: "/diseases/fd" });
    expect(splitLocale("/pl")).toEqual({ locale: "pl", pathname: "/" });
    expect(splitLocale("/pl/")).toEqual({ locale: "pl", pathname: "/" });
  });

  it("canonicalizes an explicit /en prefix away", () => {
    expect(splitLocale("/en/about")).toEqual({ locale: "en", pathname: "/about" });
  });

  it("does not treat a disease slug that starts with pl as a locale", () => {
    // "plague" etc. — only an exact "pl" segment is a locale prefix.
    expect(splitLocale("/diseases/pln-syndrome")).toEqual({
      locale: "en",
      pathname: "/diseases/pln-syndrome",
    });
  });
});

describe("withLocalePrefix", () => {
  it("leaves English paths unprefixed", () => {
    expect(withLocalePrefix("/diseases/fd", "en")).toBe("/diseases/fd");
    expect(withLocalePrefix("/", "en")).toBe("/");
  });

  it("prepends /pl for Polish", () => {
    expect(withLocalePrefix("/diseases/fd", "pl")).toBe("/pl/diseases/fd");
    expect(withLocalePrefix("/", "pl")).toBe("/pl");
  });

  it("round-trips with splitLocale", () => {
    const bare = "/diseases/fd";
    for (const locale of ["en", "pl"] as const) {
      const full = withLocalePrefix(bare, locale);
      expect(splitLocale(full)).toEqual({ locale, pathname: bare });
    }
  });
});
