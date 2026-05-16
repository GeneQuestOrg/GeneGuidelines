import { describe, expect, it } from "vitest";
import { parseHash } from "./parseHash";

describe("parseHash", () => {
  it("parses home", () => {
    expect(parseHash("#/")).toEqual({ name: "home" });
    expect(parseHash("")).toEqual({ name: "home" });
  });

  it("parses dev components", () => {
    expect(parseHash("#/dev/components")).toEqual({ name: "devComponents" });
  });

  it("parses disease index and slug", () => {
    expect(parseHash("#/diseases")).toEqual({ name: "diseaseIndex", query: undefined });
    expect(parseHash("#/diseases?q=fabry")).toEqual({ name: "diseaseIndex", query: "fabry" });
    expect(parseHash("#/diseases/fd")).toEqual({ name: "disease", slug: "fd" });
  });

  it("rejects invalid disease slugs", () => {
    expect(parseHash("#/diseases/../evil")).toEqual({ name: "home" });
    expect(parseHash("#/diseases/bad%20slug")).toEqual({ name: "home" });
  });

  it("parses nested disease routes", () => {
    expect(parseHash("#/diseases/fabry/flowchart")).toEqual({
      name: "flowchart",
      slug: "fabry",
    });
    expect(parseHash("#/diseases/fabry/guidelines")).toEqual({
      name: "guidelines",
      slug: "fabry",
    });
    expect(parseHash("#/diseases/fabry/guidelines/pr/42")).toEqual({
      name: "guidelines",
      slug: "fabry",
      prId: "42",
    });
  });

  it("parses doctors and account", () => {
    expect(parseHash("#/doctors")).toEqual({ name: "doctors" });
    expect(parseHash("#/doctors?disease=fd")).toEqual({ name: "doctors", disease: "fd" });
    expect(parseHash("#/doctor/jane-doe")).toEqual({ name: "doctor", slug: "jane-doe" });
    expect(parseHash("#/account")).toEqual({ name: "account" });
    expect(parseHash("#/about")).toEqual({ name: "about" });
  });

  it("parses trials registry page", () => {
    expect(parseHash("#/trials")).toEqual({ name: "trials" });
    expect(parseHash("#/trials?q=fibrous")).toEqual({ name: "trials", query: "fibrous" });
  });

  it("parses start research with optional disease", () => {
    expect(parseHash("#/start-research")).toEqual({ name: "startResearch" });
    expect(parseHash("#/start-research?disease=fd")).toEqual({
      name: "startResearch",
      diseaseSlug: "fd",
    });
  });

  it("parses research run with query", () => {
    expect(parseHash("#/research/run-1?q=fabry")).toEqual({
      name: "researchRun",
      id: "run-1",
      query: "fabry",
    });
    expect(parseHash("#/research/run-1?disease=fd&q=fabry")).toEqual({
      name: "researchRun",
      id: "run-1",
      query: "fabry",
      diseaseSlug: "fd",
    });
  });

  it("falls back to home for unknown paths", () => {
    expect(parseHash("#/unknown/path")).toEqual({ name: "home" });
  });
});
