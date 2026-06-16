import { describe, expect, it } from "vitest";
import { fixtureOfficialGuidelineRepository } from "./fixtureOfficialGuidelineRepository";
import { sourceDocUrl } from "../types/sourceDoc";

describe("fixtureOfficialGuidelineRepository.getShelf", () => {
  it("returns the curated FD shelf (4 documents)", async () => {
    const docs = await fixtureOfficialGuidelineRepository.getShelf("fd");
    expect(docs).toHaveLength(4);
    expect(docs.map((d) => d.id)).toEqual([
      "boyce2019",
      "gun2024",
      "szymczuk2023",
      "genereviews",
    ]);
    expect(docs.find((d) => d.id === "gun2024")?.isNew).toBe(true);
    expect(docs.find((d) => d.id === "genereviews")?.bookshelf).toBe("NBK274564");
  });

  it("returns the MAS shelf (2 documents)", async () => {
    const docs = await fixtureOfficialGuidelineRepository.getShelf("mas");
    expect(docs).toHaveLength(2);
  });

  it("returns an empty shelf for a disease without source documents", async () => {
    expect(await fixtureOfficialGuidelineRepository.getShelf("noonan")).toHaveLength(0);
    expect(await fixtureOfficialGuidelineRepository.getShelf("unknown")).toHaveLength(0);
  });
});

describe("sourceDocUrl", () => {
  it("links PMIDs to PubMed and bookshelf ids to NCBI", () => {
    expect(sourceDocUrl({ pmid: "31196103" } as never)).toBe(
      "https://pubmed.ncbi.nlm.nih.gov/31196103/",
    );
    expect(sourceDocUrl({ bookshelf: "NBK274564" } as never)).toBe(
      "https://www.ncbi.nlm.nih.gov/books/NBK274564/",
    );
  });
});
