import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  isPathwayActionNode,
  type PathwayActionNode,
  type PathwayDecisionNode,
  type PathwayNode,
} from "../../types/parentPathway";

export interface FlowNodeProps {
  node: PathwayNode;
  depth: number;
  stepNumber?: number;
  selected: PathwayActionNode | null;
  onSelect: (node: PathwayActionNode) => void;
}

export function FlowNode({ node, depth, stepNumber, selected, onSelect }: FlowNodeProps) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(stepNumber === 1 || (stepNumber == null && depth < 1));

  if (isPathwayActionNode(node)) {
    const isActive = selected?.id === node.id;
    return (
      <div className="flow-step">
        {stepNumber != null ? (
          <span className="flow-step__badge" aria-hidden>
            {stepNumber}
          </span>
        ) : null}
        <button
          type="button"
          className={`flow-action ${node.urgent ? "flow-action--urgent" : ""} ${isActive ? "is-active" : ""}`}
          onClick={() => onSelect(node)}
        >
          <span className="flow-action__arrow" aria-hidden>
            →
          </span>
          <span className="flow-action__title">{node.title}</span>
          {node.urgent ? (
            <span className="flow-action__urgent">{t("flowNode.urgent")}</span>
          ) : null}
        </button>
      </div>
    );
  }

  const decision = node as PathwayDecisionNode;
  return (
    <div className={`flow-node depth-${depth}`}>
      <button type="button" className="flow-node__head" onClick={() => setOpen(!open)}>
        {stepNumber != null ? (
          <span className="flow-step__badge flow-step__badge--inline" aria-hidden>
            {stepNumber}
          </span>
        ) : (
          <span className={`flow-node__chev ${open ? "is-open" : ""}`} aria-hidden>
            ▸
          </span>
        )}
        <span className="flow-node__title">{decision.title}</span>
        {decision.hint ? <span className="flow-node__hint">{decision.hint}</span> : null}
        {stepNumber != null ? (
          <span className={`flow-node__chev ${open ? "is-open" : ""}`} aria-hidden>
            ▸
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="flow-node__branches">
          {decision.branches.map((branch, index) => (
            <BranchRow
              key={`${decision.id}-branch-${index}`}
              branch={branch}
              depth={depth}
              selected={selected}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function BranchRow({
  branch,
  depth,
  selected,
  onSelect,
}: {
  branch: PathwayDecisionNode["branches"][number];
  depth: number;
  selected: PathwayActionNode | null;
  onSelect: (node: PathwayActionNode) => void;
}) {
  const { t } = useTranslation("common");
  return (
    <div className="flow-branch">
      <div className="flow-branch__answer">{branch.answer}</div>
      {branch.next ? (
        <FlowNode node={branch.next} depth={depth + 1} selected={selected} onSelect={onSelect} />
      ) : (
        <div className="flow-branch__terminal">{t("flowNode.terminalBranch")}</div>
      )}
    </div>
  );
}
