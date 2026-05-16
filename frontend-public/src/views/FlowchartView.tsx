import { useState } from "react";
import { Button } from "@gene-guidelines/ui";
import { ActionDetail } from "../components/flowchart/ActionDetail";
import { FlowNode } from "../components/flowchart/FlowNode";
import { PathwayAboutSection } from "../components/flowchart/PathwayAboutSection";
import { useParentPathway } from "../hooks/useParentPathway";
import type { PathwayActionNode } from "../types/parentPathway";
import "../styles/flowchart.css";

export interface FlowchartViewProps {
  slug: string;
  onNav: (path: string) => void;
}

export function FlowchartView({ slug, onNav }: FlowchartViewProps) {
  const { pathway, loading, error } = useParentPathway(slug);
  const [selected, setSelected] = useState<PathwayActionNode | null>(null);

  if (loading) {
    return (
      <div className="page page--flow">
        <p>Loading your next-steps guide…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page page--flow">
        <h2>Could not load pathway</h2>
        <p>{error}</p>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}`)}>
          Back to disease
        </Button>
      </div>
    );
  }

  if (!pathway?.tree) {
    return (
      <div className="page page--flow page--empty">
        <h2>Next-steps guide not available yet</h2>
        <p>
          A step-by-step guide for families and patients has not been generated for this
          condition yet.
        </p>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}`)}>
          Back to disease overview
        </Button>
      </div>
    );
  }

  const tree = pathway.tree;

  return (
    <div className="page page--flow">
      <div className="flow__head">
        <p className="flow__eyebrow">After diagnosis</p>
        <h1>{tree.title}</h1>
        {tree.subtitle ? <p className="flow__subtitle">{tree.subtitle}</p> : null}
        <p className="flow__hint">
          Work through the steps in order. Tap a highlighted action to see who to contact,
          what to expect, and questions you can ask — you can read them from your phone at the
          appointment.
        </p>
        {pathway.basedOn ? (
          <p className="flow__hint flow__hint--muted">Based on: {pathway.basedOn}</p>
        ) : null}
      </div>

      {tree.about ? <PathwayAboutSection about={tree.about} /> : null}

      <div className="flow__layout">
        <ol className="flow__tree flow__tree--steps">
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
        <aside className="flow__detail">
          {selected ? (
            <ActionDetail action={selected} />
          ) : (
            <div className="flow__detail-empty">
              <h3>Your next visit</h3>
              <p>
                Choose a highlighted action in the steps on the left. We will show who can help,
                what usually happens, and what to ask — so you do not have to remember
                everything alone.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
