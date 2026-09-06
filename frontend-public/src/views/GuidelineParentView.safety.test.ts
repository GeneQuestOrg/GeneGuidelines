import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import enGuidelines from "../locales/en/guidelines.json";
import plGuidelines from "../locales/pl/guidelines.json";

/**
 * Medical-honesty guard for the family-facing guideline gate.
 *
 * When a disease has no agreed guideline, the parent gate said "We've prepared an
 * early draft — show it to your doctor". For a disease with no baseline either, that
 * promised something that does not exist. It surfaced when the evidence gate
 * (ADR 005) started withholding an ungrounded synthesis: the page fell back to the
 * gate and offered a draft that was never built.
 *
 * Overclaiming to a parent is the failure mode the whole guideline layer is built to
 * avoid, so the promise must stay conditional on a draft actually existing.
 *
 * Source-level guard: this project has no component-render harness, so it asserts on
 * the render layer and the copy rather than on a mounted tree.
 */
const source = readFileSync(
  fileURLToPath(new URL("./GuidelineParentView.tsx", import.meta.url)),
  "utf8",
);

describe("parent guideline gate honesty", () => {
  it("decides from the baseline whether a draft exists", () => {
    expect(source).toMatch(/const noDraft = baseline == null;/);
  });

  it("never promises a draft when none was built", () => {
    // Both the title and the body must branch; a half-gated pair would pair an
    // honest heading with copy still describing a draft.
    expect(source).toMatch(/noDraft \? t\("gateNoSourcesTitle"\) : t\("gateTitle"\)/);
    expect(source).toMatch(/noDraft\s*\?\s*t\("gateNoSourcesBody"/);
  });

  it("hides the draft's read-state line when there is no draft", () => {
    expect(source).toMatch(/noDraft \? null : \(/);
  });

  it.each([
    ["en", enGuidelines as Record<string, string>],
    ["pl", plGuidelines as Record<string, string>],
  ])("%s copy states the reason without claiming a draft", (_locale, copy) => {
    expect(copy.gateNoSourcesTitle).toBeTruthy();
    expect(copy.gateNoSourcesBody).toBeTruthy();
    // It has to say WHY — that the literature is insufficient — not merely that a
    // guideline is missing, which the reader can already see.
    expect(copy.gateNoSourcesBody).toMatch(/wystarcz|enough/i);
    // And it must not repeat the draft promise this test exists to remove.
    expect(copy.gateNoSourcesBody).not.toMatch(/szkic|draft/i);
  });
});
