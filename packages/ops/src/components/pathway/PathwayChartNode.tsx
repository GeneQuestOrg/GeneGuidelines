import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { PathwayChartNodeData } from "../../utils/pathwayToFlow";

export function PathwayChartNode({ data }: NodeProps) {
  const d = data as PathwayChartNodeData;
  const kindClass = `ops-pp-node ops-pp-node--${d.kind}${d.urgent ? " ops-pp-node--urgent" : ""}`;

  return (
    <div className={kindClass}>
      <Handle type="target" position={Position.Top} className="ops-pp-node__handle" />
      {d.kind === "root" ? (
        <span className="ops-pp-node__badge">Patient pathway</span>
      ) : null}
      {d.kind === "decision" ? (
        <span className="ops-pp-node__badge">Question</span>
      ) : null}
      {d.kind === "action" && d.urgent ? (
        <span className="ops-pp-node__badge ops-pp-node__badge--urgent">Urgent</span>
      ) : null}
      <div className="ops-pp-node__title">{d.title}</div>
      {d.hint ? <div className="ops-pp-node__hint">{d.hint}</div> : null}
      <Handle type="source" position={Position.Bottom} className="ops-pp-node__handle" />
    </div>
  );
}
