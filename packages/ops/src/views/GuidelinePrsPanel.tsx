import { GuidelinePrsView } from "./GuidelinePrsView";
import "./workflows-workspace.css";

/** Guideline change-request review queue (Phase 14). */
export function GuidelinePrsPanel() {
  return (
    <div className="ops-prs-panel">
      <GuidelinePrsView />
    </div>
  );
}
