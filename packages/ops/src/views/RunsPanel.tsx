import { RunsView } from "./RunsView";
import "./workflows-workspace.css";

/** Pipeline runs, live agent traces, and approvals. */
export function RunsPanel() {
  return (
    <div className="ops-runs-panel">
      <RunsView />
    </div>
  );
}
