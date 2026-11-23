import { describe, expect, it } from "vitest";
import type { SourceDoc } from "../types/sourceDoc";
import { citationLine, familyDoctorMailto } from "./familyDoctorMail";

const doc = (over: Partial<SourceDoc>): SourceDoc => ({
  id: "x",
  role: "Base consensus",
  title: "Best practice management guidelines.",
  authors: "Javaid MK, Boyce A, Appelman-Dijkstra N",
  journal: "Orphanet J Rare Dis",
  year: 2019,
  scope: "",
  covers: [],
  pmid: "31196103",
  ...over,
});

describe("family doctor list", () => {
  it("writes one citation per paper, with the address a doctor can type", () => {
    expect(citationLine(doc({}), "et al.")).toBe(
      "Javaid MK et al. (2019). Best practice management guidelines. Orphanet J Rare Dis. https://pubmed.ncbi.nlm.nih.gov/31196103/",
    );
    expect(citationLine(doc({ authors: "Boyce AM, Collins MT" }), "i wsp.")).toContain("Boyce AM, Collins MT (2019)");
    expect(
      citationLine(
        doc({ pmid: undefined, bookshelf: "NBK274564", authors: "", journal: "", title: "Fibrous Dysplasia", year: "continuously updated" }),
        "et al.",
      ),
    ).toBe("Fibrous Dysplasia (continuously updated). https://www.ncbi.nlm.nih.gov/books/NBK274564/");
  });

  it("puts the whole list in a mailto with no recipient", () => {
    const href = familyDoctorMailto([doc({}), doc({ id: "y", pmid: "31673695" })], "FD – papers", "Hello,", "et al.");
    expect(href.startsWith("mailto:?subject=")).toBe(true);
    const body = decodeURIComponent(href.split("&body=")[1]);
    expect(body).toContain("Hello,");
    expect(body).toContain("https://pubmed.ncbi.nlm.nih.gov/31196103/");
    expect(body).toContain("https://pubmed.ncbi.nlm.nih.gov/31673695/");
  });
});
