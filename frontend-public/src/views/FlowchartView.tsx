import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("misc");
  const { pathway, loading, error } = useParentPathway(slug);
  const [selected, setSelected] = useState<PathwayActionNode | null>(null);

  if (loading) {
    return (
      <div className="page page--flow">
        <p>{t("flowchart.loading")}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page page--flow">
        <h2>{t("flowchart.errorTitle")}</h2>
        <p>{error}</p>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}`)}>
          {t("flowchart.backToDisease")}
        </Button>
      </div>
    );
  }

  if (!pathway?.tree) {
    return (
      <div className="page page--flow page--empty">
        <h2>{t("flowchart.notAvailableTitle")}</h2>
        <p>{t("flowchart.notAvailableDesc")}</p>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}`)}>
          {t("flowchart.backToDiseaseOverview")}
        </Button>
      </div>
    );
  }

  const tree = pathway.tree;

  return (
    <div className="page page--flow">
      <div className="flow__head">
        <p className="flow__eyebrow">{t("flowchart.eyebrow")}</p>
        <h1>{tree.title}</h1>
        {tree.subtitle ? <p className="flow__subtitle">{tree.subtitle}</p> : null}
        <p className="flow__hint">{t("flowchart.hint")}</p>
        {pathway.basedOn ? (
          <p className="flow__hint flow__hint--muted">
            {t("flowchart.basedOn", { basedOn: pathway.basedOn })}
          </p>
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
              <h3>{t("flowchart.nextVisitTitle")}</h3>
              <p>{t("flowchart.nextVisitDesc")}</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
