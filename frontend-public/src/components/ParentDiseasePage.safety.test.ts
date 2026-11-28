import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Safety guard for the parent and guest view of a disease page.
 *
 * The therapies list is an AI draft that nobody has checked against the disease's guideline. On 2026-11-28 an independent review found that for FOP it listed stretching exercises and surgery (sourced to a paper on bunions), while the FOP guideline tells families to avoid passive stretching and elective surgery. A parent cannot tell such an entry from a sound one, so the list is not rendered for parents and guests at all; clinicians still see it in their own view.
 *
 * If therapies come back to this page, they come back behind a check against the guideline, and this test is changed on purpose.
 */
describe("ParentDiseasePage does not show therapies to parents and guests", () => {
  const source = readFileSync(fileURLToPath(new URL("./ParentDiseasePage.tsx", import.meta.url)), "utf8");

  it("neither loads nor renders the therapies list", () => {
    expect(source).not.toMatch(/useDiseaseTherapies/);
    expect(source).not.toMatch(/TherapiesList/);
  });
});
