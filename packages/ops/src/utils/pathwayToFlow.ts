import { Position, type Edge, type Node } from "@xyflow/react";
import {
  isPathwayActionNode,
  type ParentPathwayTree,
  type PathwayActionNode,
  type PathwayNode,
} from "../types/parentPathway";

export type PathwayChartNodeKind = "root" | "decision" | "action" | "terminal";

export type PathwayChartNodeData = {
  kind: PathwayChartNodeKind;
  title: string;
  hint?: string;
  urgent?: boolean;
  action?: PathwayActionNode;
};

const SPINE_W = 300;
const ROOT_W = 300;
const V_GAP = 52;
const STEP_GAP = 20;
const NODE_BLOCK_H = 64;

function placeOnSpine(
  node: PathwayNode | null,
  y: number,
  parentId: string | null,
  edgeLabel: string | undefined,
  nodes: Node<PathwayChartNodeData>[],
  edges: Edge[],
  idPath: string,
): number {
  if (!node) {
    return y;
  }

  if (isPathwayActionNode(node)) {
    const id = `${idPath}-${node.id}`;
    nodes.push({
      id,
      type: "pathwayChart",
      position: { x: -SPINE_W / 2, y },
      data: {
        kind: "action",
        title: node.title,
        urgent: node.urgent,
        action: node,
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });
    if (parentId) {
      edges.push({
        id: `${parentId}->${id}`,
        source: parentId,
        target: id,
        label: edgeLabel,
        type: "smoothstep",
      });
    }
    return y + NODE_BLOCK_H + V_GAP;
  }

  const decision = node;
  const id = `${idPath}-${decision.id}`;
  nodes.push({
    id,
    type: "pathwayChart",
    position: { x: -SPINE_W / 2, y },
    data: {
      kind: "decision",
      title: decision.title,
      hint: decision.hint,
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  if (parentId) {
    edges.push({
      id: `${parentId}->${id}`,
      source: parentId,
      target: id,
      label: edgeLabel,
      type: "smoothstep",
    });
  }

  let cursorY = y + NODE_BLOCK_H + 8;
  for (const [index, branch] of decision.branches.entries()) {
    if (!branch.next) {
      continue;
    }
    cursorY = placeOnSpine(
      branch.next,
      cursorY,
      id,
      branch.answer,
      nodes,
      edges,
      `${idPath}-b${index}`,
    );
    cursorY += 8;
  }
  return cursorY + V_GAP;
}

/** Single-column top-to-bottom layout for parent next-steps (no wide parallel fan-out). */
export function pathwayTreeToFlow(
  tree: ParentPathwayTree,
): { nodes: Node<PathwayChartNodeData>[]; edges: Edge[] } {
  const nodes: Node<PathwayChartNodeData>[] = [];
  const edges: Edge[] = [];

  const rootId = `root-${tree.id}`;
  nodes.push({
    id: rootId,
    type: "pathwayChart",
    position: { x: -ROOT_W / 2, y: 0 },
    data: {
      kind: "root",
      title: tree.title,
      hint: tree.subtitle,
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  let y = NODE_BLOCK_H + V_GAP;
  tree.children.forEach((child, index) => {
    y = placeOnSpine(child, y, rootId, undefined, nodes, edges, `s${index}`);
    y += STEP_GAP;
  });

  return { nodes, edges };
}
