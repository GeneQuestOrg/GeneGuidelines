import { useState } from "react";
import {
  parseParentPathwayTree,
  type ParentPathwayTree,
} from "../../types/parentPathway";
import { PathwayFlowPreview } from "./PathwayFlowPreview";
import "../../styles/ops-pathway-preview.css";

export type PathwayPreviewMode = "chart" | "json";

export interface SavedPathwayPreviewProps {
  tree: unknown;
}

function extractPathwayOverview(tree: unknown): {
  aboutTitle?: string;
  aboutParagraphs: string[];
} {
  if (!tree || typeof tree !== "object") {
    return { aboutParagraphs: [] };
  }
  const o = tree as Record<string, unknown>;
  const about = o.about;
  let aboutTitle: string | undefined;
  const aboutParagraphs: string[] = [];
  if (about && typeof about === "object") {
    const ab = about as Record<string, unknown>;
    if (typeof ab.title === "string" && ab.title.trim()) {
      aboutTitle = ab.title.trim();
    }
    const summary = ab.summary;
    if (typeof summary === "string" && summary.trim()) {
      aboutParagraphs.push(
        ...summary
          .split(/\n\n+/)
          .map((p) => p.trim())
          .filter(Boolean),
      );
    }
  }
  return {
    aboutTitle,
    aboutParagraphs,
  };
}

export function SavedPathwayPreview({ tree }: SavedPathwayPreviewProps) {
  const [mode, setMode] = useState<PathwayPreviewMode>("chart");
  const parsed = parseParentPathwayTree(tree) as ParentPathwayTree | null;
  const overview = extractPathwayOverview(tree);
  const hasOverview = Boolean(overview.aboutTitle || overview.aboutParagraphs.length);

  return (
    <section className="ops-guideline-preview" aria-label="Saved patient chart preview">
      <div className="ops-pp-preview__head">
        <h3 className="ops-guideline-preview__heading">Saved patient chart (preview)</h3>
        <div className="ops-pp-preview__toggle" role="tablist" aria-label="Preview mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "chart"}
            className={`ops-pp-preview__tab ${mode === "chart" ? "is-active" : ""}`}
            onClick={() => setMode("chart")}
          >
            Chart
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "json"}
            className={`ops-pp-preview__tab ${mode === "json" ? "is-active" : ""}`}
            onClick={() => setMode("json")}
          >
            JSON
          </button>
        </div>
      </div>

      <p className="ops-pp-preview__chart-hint">
        <strong>Chart:</strong> boxes are next steps. Click a box to show specialist role, what to expect,
        and suggested questions on the right. <strong>JSON</strong> shows the exact payload saved as draft.
      </p>

      {hasOverview ? (
        <div className="ops-pp-preview__overview">
          {overview.aboutTitle ? (
            <h4 className="ops-pp-preview__overview-about-head">{overview.aboutTitle}</h4>
          ) : null}
          {overview.aboutParagraphs.map((para, i) => (
            <p key={i} className="ops-pp-preview__overview-p">
              {para}
            </p>
          ))}
        </div>
      ) : null}

      {mode === "chart" ? (
        parsed ? (
          <PathwayFlowPreview tree={parsed} />
        ) : (
          <p className="ops-pp-preview__fallback">
            Could not render chart — tree shape is invalid. Switch to JSON to inspect raw data.
          </p>
        )
      ) : (
        <pre className="ops-raw-output">{JSON.stringify(tree, null, 2)}</pre>
      )}
    </section>
  );
}
