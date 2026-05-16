/** Parent/caregiver decision-tree — mirrors backend ParentPathwayResponse.tree */

export type PathwayBranch = {
  answer: string;
  next: PathwayNode | null;
};

export type PathwayActionNode = {
  id: string;
  action: true;
  title: string;
  specialty: string;
  whatToExpect?: string;
  questions: string[];
  urgent?: boolean;
  citations?: string[];
  doctorHint?: string;
  evidenceGap?: boolean;
};

export type PathwayDecisionNode = {
  id: string;
  title: string;
  hint?: string;
  branches: PathwayBranch[];
  action?: false;
};

export type PathwayNode = PathwayActionNode | PathwayDecisionNode;

export function isPathwayActionNode(node: PathwayNode): node is PathwayActionNode {
  return Boolean((node as PathwayActionNode).action);
}

export type ParentPathwayTree = {
  id: string;
  title: string;
  subtitle?: string;
  locale?: string;
  basedOn?: string;
  sourceRunId?: string;
  children: PathwayNode[];
};

export function parseParentPathwayTree(raw: unknown): ParentPathwayTree | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const o = raw as Record<string, unknown>;
  if (typeof o.id !== "string" || typeof o.title !== "string") {
    return null;
  }
  if (!Array.isArray(o.children)) {
    return null;
  }
  return raw as ParentPathwayTree;
}
