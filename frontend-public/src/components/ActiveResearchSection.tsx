import { Section } from "@gene-guidelines/ui";
import type { ResearchRun } from "../types/researchRun";
import "./active-research.css";

export interface ActiveResearchSectionProps {
  runs: readonly ResearchRun[];
  onNav: (path: string) => void;
}

function formatElapsed(seconds: number | null): string {
  if (seconds == null || seconds < 0) {
    return "just started";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes < 60) {
    return remaining === 0 ? `${minutes} min` : `${minutes}m ${remaining}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function targetForRun(run: ResearchRun): string {
  if (run.diseaseSlug != null && run.diseaseSlug !== "") {
    return `/diseases/${run.diseaseSlug}`;
  }
  return "/diseases";
}

export function ActiveResearchSection({
  runs,
  onNav,
}: ActiveResearchSectionProps) {
  if (runs.length === 0) {
    return null;
  }
  return (
    <Section title="Active research" count={runs.length}>
      <div className="active-research__grid">
        {runs.map((run) => {
          const href = `#${targetForRun(run)}`;
          return (
            <a
              key={run.runId}
              href={href}
              className="active-research__card"
              onClick={(e) => {
                e.preventDefault();
                onNav(targetForRun(run));
              }}
            >
              <div className="active-research__top">
                <span className="active-research__dot" aria-hidden />
                <span className="active-research__flow">
                  {run.flowKey.replace(/_/g, " ")}
                </span>
                <span className="active-research__elapsed">
                  {formatElapsed(run.elapsedSec)}
                </span>
              </div>
              <h3 className="active-research__title">{run.label}</h3>
              <p className="active-research__cta">Watch live →</p>
            </a>
          );
        })}
      </div>
    </Section>
  );
}
