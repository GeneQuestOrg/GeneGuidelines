import { describe, expect, it } from "vitest";
import {
  type LocalParentRec,
  appendLocalRec,
  readLocalRecs,
} from "./localParentRecs";

const rec: LocalParentRec = {
  text: "Helped us avoid an unnecessary operation.",
  region: "woj. wielkopolskie",
  relation: "parent",
  date: "2026-06-12",
};

describe("readLocalRecs", () => {
  it("returns an empty list for empty storage", () => {
    expect(readLocalRecs(null, "dowgierd")).toEqual([]);
    expect(readLocalRecs("{}", "dowgierd")).toEqual([]);
  });

  it("returns the recommendations stored for the given doctor slug", () => {
    const raw = JSON.stringify({ dowgierd: [rec], allecou: [] });
    expect(readLocalRecs(raw, "dowgierd")).toEqual([rec]);
    expect(readLocalRecs(raw, "allecou")).toEqual([]);
    expect(readLocalRecs(raw, "missing")).toEqual([]);
  });

  it("returns an empty list for corrupted JSON, never throwing", () => {
    expect(readLocalRecs("{not json", "dowgierd")).toEqual([]);
    expect(readLocalRecs("[]", "dowgierd")).toEqual([]);
    expect(readLocalRecs("42", "dowgierd")).toEqual([]);
  });

  it("drops malformed entries and defaults a bad relation to parent", () => {
    const raw = JSON.stringify({
      dowgierd: [
        { text: "ok", date: "2026-06-12", relation: "weird" },
        { date: "2026-06-12" },
        "garbage",
      ],
    });
    expect(readLocalRecs(raw, "dowgierd")).toEqual([
      { text: "ok", region: "", relation: "parent", date: "2026-06-12" },
    ]);
  });
});

describe("appendLocalRec", () => {
  it("appends to an empty store", () => {
    const next = appendLocalRec(null, "dowgierd", rec);
    expect(readLocalRecs(next, "dowgierd")).toEqual([rec]);
  });

  it("preserves recommendations for other doctors", () => {
    const start = appendLocalRec(null, "allecou", rec);
    const next = appendLocalRec(start, "dowgierd", rec);
    expect(readLocalRecs(next, "allecou")).toEqual([rec]);
    expect(readLocalRecs(next, "dowgierd")).toEqual([rec]);
  });

  it("appends after existing recommendations for the same doctor", () => {
    const start = appendLocalRec(null, "dowgierd", rec);
    const second: LocalParentRec = { ...rec, text: "A second note from another family." };
    const next = appendLocalRec(start, "dowgierd", second);
    expect(readLocalRecs(next, "dowgierd")).toEqual([rec, second]);
  });

  it("treats corrupted current contents as an empty store", () => {
    const next = appendLocalRec("{not json", "dowgierd", rec);
    expect(readLocalRecs(next, "dowgierd")).toEqual([rec]);
  });
});
