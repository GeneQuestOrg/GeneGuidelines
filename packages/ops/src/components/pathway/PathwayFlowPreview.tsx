import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ParentPathwayTree, PathwayActionNode } from "../../types/parentPathway";
import { pathwayTreeToFlow, type PathwayChartNodeData } from "../../utils/pathwayToFlow";
import { PathwayActionDetail } from "./PathwayActionDetail";
import { PathwayChartNode } from "./PathwayChartNode";

const nodeTypes = { pathwayChart: PathwayChartNode };

export interface PathwayFlowPreviewProps {
  tree: ParentPathwayTree;
}

export function PathwayFlowPreview({ tree }: PathwayFlowPreviewProps) {
  const layout = useMemo(() => pathwayTreeToFlow(tree), [tree]);
  const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges);
  const [selectedAction, setSelectedAction] = useState<PathwayActionNode | null>(null);

  useEffect(() => {
    setNodes(layout.nodes);
    setEdges(layout.edges);
    const firstActionNode = layout.nodes.find(
      (n): n is Node<PathwayChartNodeData> =>
        n.data?.kind === "action" && n.data.action != null,
    );
    setSelectedAction(firstActionNode?.data.action ?? null);
  }, [layout, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<PathwayChartNodeData>) => {
      const action = node.data.action;
      setSelectedAction(action ?? null);
    },
    [],
  );

  return (
    <div className="ops-pp-flow">
      <div className="ops-pp-flow__canvas" aria-label="Pathway flowchart">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          fitView
          fitViewOptions={{ padding: 0.35, maxZoom: 0.95 }}
          minZoom={0.25}
          maxZoom={1.25}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        </ReactFlow>
      </div>
      <aside className="ops-pp-flow__detail">
        {selectedAction ? (
          <PathwayActionDetail action={selectedAction} />
        ) : (
          <p className="ops-pp-flow__detail-empty">
            Click an action node in the chart to see specialist, visit expectations, and
            questions.
          </p>
        )}
      </aside>
    </div>
  );
}
