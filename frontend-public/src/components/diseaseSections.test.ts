import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  FD_TEST_ROW_COUNT,
  diseaseSectionTabs,
  hasGuidelineSummary,
  hasTestsSheet,
} from "./diseaseSections";

/**
 * The tab strip under the disease card links to real pages, and shows a tab only when that page has something for this disease: the printable list of tests exists for FD alone, and the guideline tab needs a summary the guideline page will actually show.
 */
describe("disease section tabs", () => {
  it("gives FD with a summary all three tabs, in order", () => {
    expect(diseaseSectionTabs("fd", { summary: true })).toEqual([
      { id: "start", path: "/diseases/fd" },
      { id: "tests", path: "/diseases/fd/tests" },
      { id: "guidelines", path: "/diseases/fd/guidelines" },
    ]);
  });

  it("gives no other disease a list of tests", () => {
    expect(hasTestsSheet("mas")).toBe(false);
    expect(diseaseSectionTabs("mas", { summary: true }).map((tab) => tab.id)).toEqual([
      "start",
      "guidelines",
    ]);
  });

  it("leaves the guideline tab out when there is no summary to show", () => {
    expect(diseaseSectionTabs("noonan", { summary: false }).map((tab) => tab.id)).toEqual(["start"]);
    expect(diseaseSectionTabs("fd", { summary: false }).map((tab) => tab.id)).toEqual(["start", "tests"]);
  });

  it("counts a summary the way the guideline page does: present and not pending", () => {
    expect(hasGuidelineSummary(null)).toBe(false);
    expect(hasGuidelineSummary({ status: "pending" })).toBe(false);
    expect(hasGuidelineSummary({ status: "draft" })).toBe(true);
    expect(hasGuidelineSummary({ status: "consensus" })).toBe(true);
  });

  it("promises as many tests as the printable list renders", () => {
    const sheet = readFileSync(fileURLToPath(new URL("./FdTestsSheet.tsx", import.meta.url)), "utf8");
    const rendered = (sheet.match(/const ROW_IDS = \[([\s\S]*?)\] as const;/)?.[1] ?? "")
      .split(",")
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0);
    expect(rendered.length).toBeGreaterThan(0);
    expect(FD_TEST_ROW_COUNT).toBe(rendered.length);
  });
});
