import { describe, expect, it } from "vitest";
import { pubmedArticleUrl } from "./pubmedUrl";

describe("pubmedArticleUrl", () => {
  it("builds PubMed URL from PMID", () => {
    expect(pubmedArticleUrl("31196103")).toBe(
      "https://pubmed.ncbi.nlm.nih.gov/31196103/",
    );
  });

  it("strips non-digits", () => {
    expect(pubmedArticleUrl("PMID: 12345")).toBe(
      "https://pubmed.ncbi.nlm.nih.gov/12345/",
    );
  });

  it("falls back to base URL when empty", () => {
    expect(pubmedArticleUrl("")).toBe("https://pubmed.ncbi.nlm.nih.gov");
  });
});
