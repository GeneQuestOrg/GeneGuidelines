import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import enParent from "../locales/en/parent.json";
import plParent from "../locales/pl/parent.json";

/**
 * Medical-safety guard for the family-facing disease page (`/diseases/{slug}`).
 *
 * The founder rule: the disease/guideline surface shows only HARD, source-grounded
 * data. The static, hand-seeded "Red flags — when to seek a second opinion" block
 * asserted clinical claims with no citation (one wrongly implied that genetic
 * confirmation is mandatory), so it must NOT render on the disease page. The copy
 * data stays in `parent.json` (reversible) — it is simply no longer rendered.
 *
 * This is an absence/presence guard on the render layer (there is no component-render
 * harness in this project), so it stays deterministic and only fails if someone
 * re-introduces the unsourced block or removes the source shelf.
 */
const diseaseTabsSource = readFileSync(
  fileURLToPath(new URL("./DiseaseTabs.tsx", import.meta.url)),
  "utf8",
);

describe("DiseaseTabs medical-safety", () => {
  it("does not render the unsourced red-flags block on the disease page", () => {
    // Assert on render-only tokens (the CSS class and the `.map` render), not the
    // bare identifier, so the explanatory comment mentioning `copy.redFlags` is fine.
    expect(diseaseTabsSource).not.toContain("path__redflags");
    expect(diseaseTabsSource).not.toMatch(/copy\.redFlags\.map/);
  });

  it("keeps the source shelf (Materials for the family doctor) — hard, cited data", () => {
    expect(diseaseTabsSource).toContain("familyDoctorTitle");
    expect(diseaseTabsSource).toContain("CompactSourceShelf");
  });

  it("preserves the red-flags copy data in both locales so removal is reversible", () => {
    expect(Array.isArray(enParent.redFlags)).toBe(true);
    expect(enParent.redFlags.length).toBeGreaterThan(0);
    expect(typeof enParent.redFlagsTitle).toBe("string");
    // PL locale must keep a parallel key set (matching array length).
    expect(Array.isArray(plParent.redFlags)).toBe(true);
    expect(plParent.redFlags.length).toBe(enParent.redFlags.length);
    expect(typeof plParent.redFlagsTitle).toBe("string");
  });
});
