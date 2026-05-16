import type { ParentPathwayTree, PathwayNode } from "../types/parentPathway";
import { isPathwayActionNode } from "../types/parentPathway";

function walkPathwayNode(node: PathwayNode, out: Set<string>): void {
  if (isPathwayActionNode(node)) {
    for (const raw of node.citations ?? []) {
      const pmid = String(raw).trim();
      if (pmid) {
        out.add(pmid);
      }
    }
    return;
  }
  for (const branch of node.branches) {
    if (branch.next != null) {
      walkPathwayNode(branch.next, out);
    }
  }
}

/** PMIDs cited on pathway action steps (order: depth-first over top-level children). */
export function collectPathwayCitedPmids(tree: ParentPathwayTree): string[] {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const child of tree.children) {
    const acc = new Set<string>();
    walkPathwayNode(child, acc);
    for (const pmid of acc) {
      if (!seen.has(pmid)) {
        seen.add(pmid);
        order.push(pmid);
      }
    }
  }
  return order;
}
