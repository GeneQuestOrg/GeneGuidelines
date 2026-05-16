import { describe, expect, it } from "vitest";
import { isPathwayActionNode, type PathwayActionNode } from "./parentPathway";

describe("isPathwayActionNode", () => {
  it("detects action nodes", () => {
    const action: PathwayActionNode = {
      id: "a1",
      action: true,
      title: "See specialist",
      specialty: "Pediatrics",
      questions: ["What test first?"],
    };
    expect(isPathwayActionNode(action)).toBe(true);
    expect(isPathwayActionNode({ id: "d1", title: "Pain?", branches: [] })).toBe(false);
  });
});
