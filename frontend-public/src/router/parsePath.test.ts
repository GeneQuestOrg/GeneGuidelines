import { describe, expect, it } from "vitest";
import { parsePath } from "./parsePath";

describe("parsePath", () => {
  it("parses home", () => {
    expect(parsePath("/", "")).toEqual({ name: "home" });
    expect(parsePath("", "")).toEqual({ name: "home" });
  });

  it("parses dev components", () => {
    expect(parsePath("/dev/components", "")).toEqual({ name: "devComponents" });
  });

  it("parses disease index and slug", () => {
    expect(parsePath("/diseases", "")).toEqual({ name: "diseaseIndex", query: undefined });
    expect(parsePath("/diseases", "?q=fabry")).toEqual({ name: "diseaseIndex", query: "fabry" });
    expect(parsePath("/diseases/fd", "")).toEqual({ name: "disease", slug: "fd" });
    expect(parsePath("/diseases/fd", "?alert=confirmed")).toEqual({
      name: "disease",
      slug: "fd",
      alert: "confirmed",
    });
  });

  it("rejects invalid disease slugs", () => {
    expect(parsePath("/diseases/../evil", "")).toEqual({ name: "home" });
    expect(parsePath("/diseases/bad%20slug", "")).toEqual({ name: "home" });
  });

  it("parses nested disease routes", () => {
    expect(parsePath("/diseases/fabry/flowchart", "")).toEqual({
      name: "flowchart",
      slug: "fabry",
    });
    expect(parsePath("/diseases/fabry/my-case", "")).toEqual({
      name: "myCase",
      slug: "fabry",
    });
    expect(parsePath("/diseases/fabry/guidelines", "")).toEqual({
      name: "guidelines",
      slug: "fabry",
    });
    expect(parsePath("/diseases/fabry/guidelines/pr/42", "")).toEqual({
      name: "guidelines",
      slug: "fabry",
      prId: "42",
    });
    expect(parsePath("/diseases/fabry/guidelines/source/dx-ct", "")).toEqual({
      name: "guidelines",
      slug: "fabry",
      srcParaId: "dx-ct",
    });
    expect(parsePath("/diseases/fabry/bibliography", "")).toEqual({
      name: "bibliography",
      slug: "fabry",
    });
  });

  it("parses doctors and account", () => {
    expect(parsePath("/doctors", "")).toEqual({ name: "doctors" });
    expect(parsePath("/doctors", "?disease=fd")).toEqual({ name: "doctors", disease: "fd" });
    expect(parsePath("/doctor/jane-doe", "")).toEqual({ name: "doctor", slug: "jane-doe" });
    expect(parsePath("/account", "")).toEqual({ name: "account" });
    expect(parsePath("/about", "")).toEqual({ name: "about" });
  });

  it("parses doctor invite landing", () => {
    expect(parsePath("/join/abc123", "")).toEqual({ name: "join", token: "abc123" });
    // A bare /join with no token is not a join route.
    expect(parsePath("/join", "")).toEqual({ name: "home" });
  });

  it("parses the trials browser with optional disease facet", () => {
    expect(parsePath("/trials", "")).toEqual({ name: "trials" });
    expect(parsePath("/trials", "?disease=fd")).toEqual({ name: "trials", disease: "fd" });
    // A non-disease query param (e.g. a stale ?q=) leaves the disease facet unset.
    expect(parsePath("/trials", "?q=fibrous")).toEqual({ name: "trials" });
  });

  it("parses start research with optional disease", () => {
    expect(parsePath("/start-research", "")).toEqual({ name: "startResearch" });
    expect(parsePath("/start-research", "?disease=fd")).toEqual({
      name: "startResearch",
      diseaseSlug: "fd",
    });
  });

  it("maps legacy add-disease path to start research", () => {
    expect(parsePath("/add-disease", "")).toEqual({ name: "startResearch" });
  });

  it("parses research run with query", () => {
    expect(parsePath("/research/run-1", "?q=fabry")).toEqual({
      name: "researchRun",
      id: "run-1",
      query: "fabry",
    });
    expect(parsePath("/research/run-1", "?disease=fd&q=fabry")).toEqual({
      name: "researchRun",
      id: "run-1",
      query: "fabry",
      diseaseSlug: "fd",
    });
    expect(parsePath("/research/live", "?disease=fd&name=FD")).toEqual({
      name: "researchRun",
      id: "live",
      diseaseSlug: "fd",
      diseaseName: "FD",
    });
  });

  it("falls back to home for unknown paths", () => {
    expect(parsePath("/unknown/path", "")).toEqual({ name: "home" });
  });
});
