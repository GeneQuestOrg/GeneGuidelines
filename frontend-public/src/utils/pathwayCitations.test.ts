import { describe, expect, it } from "vitest";
import { collectPathwayCitedPmids } from "./pathwayCitations";
import type { ParentPathwayTree } from "../types/parentPathway";

describe("collectPathwayCitedPmids", () => {
  it("collects PMIDs from action steps in order", () => {
    const tree: ParentPathwayTree = {
      id: "root",
      title: "T",
      children: [
        {
          id: "a1",
          action: true,
          title: "One",
          specialty: "S",
          questions: [],
          citations: ["11111111"],
        },
        {
          id: "a2",
          action: true,
          title: "Two",
          specialty: "S",
          questions: [],
          citations: ["22222222", "11111111"],
        },
      ],
    };
    expect(collectPathwayCitedPmids(tree)).toEqual(["11111111", "22222222"]);
  });
});
