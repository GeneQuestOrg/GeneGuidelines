import { useTranslation } from "react-i18next";
import { Section } from "@gene-guidelines/ui";
import type { ResearchRun } from "../types/researchRun";
import { hrefForActiveResearchRun } from "../utils/activeResearchNav";
import { groupActiveResearchRuns } from "../utils/activeResearchGroups";
import { blockedBadgeLabel } from "../utils/queuedRun";
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

function workstreamSummary(count: number): string {
  return count === 1 ? "1 workstream" : `${count} workstreams`;
}

export function ActiveResearchSection({
  runs,
  onNav,
}: ActiveResearchSectionProps) {
  const { t } = useTranslation("common");
  // Group per disease: one "run research" fans out into several backend runs
  // (guideline + finders), and the home feed must show one card per disease,
  // not a separate tile per worker.
  const groups = groupActiveResearchRuns(runs);
  if (groups.length === 0) {
    return null;
  }
  return (
    <Section title="Active research" count={groups.length}>
      <div className="active-research__grid">
        {groups.map((group) => {
          const path = hrefForActiveResearchRun(group.primaryRun);
          const href = `#${path}`;
          const blockedDescriptor = blockedBadgeLabel(group.blockedReason);
          const blockedLabel = blockedDescriptor != null ? t(blockedDescriptor.key) : null;
          return (
            <a
              key={group.key}
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
                  {workstreamSummary(group.workstreamCount)}
                </span>
                <span className="active-research__elapsed">
                  {formatElapsed(group.elapsedSec)}
                </span>
              </div>
              <h3 className="active-research__title">{group.label}</h3>
              {blockedLabel ? (
                <span className="active-research__blocked">{blockedLabel}</span>
              ) : null}
              <p className="active-research__cta">Watch live →</p>
            </a>
          );
        })}
      </div>
    </Section>
  );
}
