import type { Node, NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { NODE_STYLES } from "../data/nodeStyles";
import type { FlowNode } from "../types";

export type StageNodeData = {
  flowNode: FlowNode;
};

export type StageNodeType = Node<StageNodeData, "stage">;

export function StageNode(props: NodeProps<StageNodeType>) {
  const { data, selected } = props;
  const { flowNode } = data;
  const s =
    NODE_STYLES[flowNode.type] ?? NODE_STYLES.action;

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div
        style={{
          width: 420,
          background: "white",
          border: `2px solid ${selected ? s.color : s.border}`,
          borderRadius: 10,
          boxShadow: selected
            ? `0 0 0 4px ${s.color}22, 0 4px 12px rgba(0,0,0,0.08)`
            : "0 2px 6px rgba(0,0,0,0.04)",
          transition: "all 0.15s",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "10px 14px",
            borderBottom: `1px solid ${s.border}`,
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: selected ? s.bg : "white",
          }}
        >
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: s.dot,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: "#1e293b",
            }}
          >
            {flowNode.label}
          </span>
          <span
            style={{
              marginLeft: "auto",
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              color: s.color,
              opacity: 0.7,
            }}
          >
            {s.label}
          </span>
        </div>
        <div
          style={{
            padding: "10px 14px",
            fontSize: 12.5,
            color: "#64748b",
            lineHeight: 1.45,
          }}
        >
          {flowNode.desc}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </>
  );
}
