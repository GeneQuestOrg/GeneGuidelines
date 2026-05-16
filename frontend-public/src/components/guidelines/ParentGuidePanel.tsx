import { Button } from "@gene-guidelines/ui";
import { PathwayAboutSection } from "../flowchart/PathwayAboutSection";
import { FlowNode } from "../flowchart/FlowNode";
import type { ParentPathway } from "../../types/parentPathway";
import type { PathwayActionNode } from "../../types/parentPathway";
import { useState } from "react";

export interface ParentGuidePanelProps {
  pathway: ParentPathway;
  slug: string;
  onNav: (path: string) => void;
}

export function ParentGuidePanel({ pathway, slug, onNav }: ParentGuidePanelProps) {
  const tree = pathway.tree;
  const [selected, setSelected] = useState<PathwayActionNode | null>(null);

  return (
    <section className="gl__parent-guide" aria-labelledby="gl-patient-guide-title">
      <div className="gl__parent-guide-head">
        <h2 id="gl-patient-guide-title">{tree.title}</h2>
        {tree.subtitle ? <p className="gl__parent-guide-sub">{tree.subtitle}</p> : null}
        <Button
          type="button"
          variant="primary"
          onClick={() => onNav(`/diseases/${slug}/flowchart`)}
        >
          Open full step-by-step guide
        </Button>
      </div>

      {tree.about ? <PathwayAboutSection about={tree.about} /> : null}

      <ol className="flow__tree flow__tree--steps gl__parent-steps">
        {tree.children.map((child, index) => (
          <li key={child.id} className="flow__tree-item">
            <FlowNode
              node={child}
              depth={0}
              stepNumber={index + 1}
              selected={selected}
              onSelect={setSelected}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}
