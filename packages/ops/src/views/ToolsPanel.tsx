import { GovernanceView } from "../components/GovernanceView";
import "./workflows-workspace.css";

/** MCP tool catalog, approval modes, and builder queue. */
export function ToolsPanel() {
  return (
    <div className="ops-tools-panel">
      <GovernanceView />
    </div>
  );
}
