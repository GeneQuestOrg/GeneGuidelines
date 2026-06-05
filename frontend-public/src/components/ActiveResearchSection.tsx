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

function liveRunPath(run: ResearchRun): string {
  const base = `/research/${encodeURIComponent(run.runId)}`;
  if (run.diseaseSlug != null && run.diseaseSlug !== "") {
    return `${base}?disease=${encodeURIComponent(run.diseaseSlug)}`;
  }
  return base;
}

function progressPct(run: ResearchRun): number {
  const raw = run.progressPct;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return Math.min(99, Math.max(5, Math.round(raw)));
  }
  return 12;
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
          const path = liveRunPath(run);
          const href = `#${path}`;
          const pct = progressPct(run);
          const activity =
            run.activity != null && run.activity.trim() !== ""
              ? run.activity
              : "Research in progress…";
          return (
            <a
              key={run.runId}
              href={href}
              className="active-research__card"
              onClick={(e) => {
                e.preventDefault();
                onNav(path);
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
              <p className="active-research__activity">{activity}</p>
              <div
                className="active-research__progress"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${pct}% estimated progress`}
              >
                <div
                  className="active-research__progress-fill"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="active-research__cta">Watch live trace →</p>
            </a>
          );
        })}
      </div>
    </Section>
  );
}
