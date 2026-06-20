import { describe, expect, it } from "vitest";
import { DISEASES } from "./diseases";
import { GUIDELINE_DOCUMENTS } from "./guidelineDocuments";
import { fixtureDiseaseRepository } from "../repositories/fixtureDiseaseRepository";

/**
 * Consent guard (memory: "Consent is grant-proposal-only — do NOT name them on
 * public surfaces"). Researcher/consultant names must never serialise into the
 * public disease or guideline data — institution-level labels only. This guard
 * mirrors the existing guideline-synthesis/baseline name guards and closes the
 * gap that let "Dr. N. Appelman-Dijkstra · Dr. M. Riminucci" leak onto the
 * disease card via `statusBy`.
 */

// Consultant names that are consent-restricted on public surfaces, plus the
// generic clinician honorific that should never tag a public provenance line.
const FORBIDDEN = [/Dr\. /, /Appelman-Dijkstra/, /Riminucci/, /Hsiao/, /Dowgierd/];

function assertNoNames(label: string, serialized: string): void {
  for (const pattern of FORBIDDEN) {
    expect(serialized, `${label} must not contain ${pattern}`).not.toMatch(pattern);
  }
}

describe("consent scrub — no researcher names on public disease surfaces", () => {
  it("DISEASES catalog carries no reviewer names (no statusBy name channel)", () => {
    assertNoNames("DISEASES", JSON.stringify(DISEASES));
    // The leaking field is gone from the data entirely.
    for (const disease of DISEASES) {
      expect(disease).not.toHaveProperty("statusBy");
    }
  });

  it("fixture disease repository surface carries no reviewer names", async () => {
    const list = await fixtureDiseaseRepository.listDiseases();
    assertNoNames("listDiseases()", JSON.stringify(list));
    const fd = await fixtureDiseaseRepository.getDiseaseBySlug("fd");
    assertNoNames("getDiseaseBySlug(fd)", JSON.stringify(fd));
  });

  it("guideline documents (reader provenance) carry no reviewer names", () => {
    assertNoNames("GUIDELINE_DOCUMENTS", JSON.stringify(GUIDELINE_DOCUMENTS));
  });
});
