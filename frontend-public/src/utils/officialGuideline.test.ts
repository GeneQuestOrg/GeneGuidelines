import { describe, expect, it } from "vitest";
import { hasOfficialGuideline } from "./officialGuideline";
import type { OfficialGuideline } from "../types/officialGuideline";

const fdConsensus: OfficialGuideline = {
  diseaseSlug: "fd",
  title: "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome",
  authors: "Javaid MK, et al.",
  year: 2019,
  journal: "Orphanet J Rare Dis",
  pmid: "31196103",
  url: "https://pubmed.ncbi.nlm.nih.gov/31196103/",
  summary: "",
  confirmedBy: "find-the-consensus",
  confirmedAt: "2026-05-10",
  source: "workflow",
};

describe("hasOfficialGuideline", () => {
  it("counts a recorded guideline even while the disease is still pending (FD)", () => {
    expect(hasOfficialGuideline({ status: "pending" }, fdConsensus)).toBe(true);
  });

  it("says no guideline only when there is neither a pointer nor a non-pending status", () => {
    expect(hasOfficialGuideline({ status: "pending" }, null)).toBe(false);
  });

  it("keeps trusting a non-pending status without a pointer", () => {
    expect(hasOfficialGuideline({ status: "consensus" }, null)).toBe(true);
  });
});
