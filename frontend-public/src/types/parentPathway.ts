/** Parent/caregiver decision-tree chart — mirrors backend ParentPathwayResponse.tree */

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

export type PathwayAbout = {
  title: string;
  summary: string;
};

export type ParentPathwayTree = {
  id: string;
  title: string;
  subtitle?: string;
  about?: PathwayAbout;
  locale?: string;
  basedOn?: string;
  sourceRunId?: string;
  children: PathwayNode[];
};

export type ParentPathway = {
  diseaseSlug: string;
  locale: string;
  version: string;
  basedOn: string;
  generatedAt: string;
  sourceGuidelineVersion?: string | null;
  sourceRunId?: string | null;
  tree: ParentPathwayTree;
};
