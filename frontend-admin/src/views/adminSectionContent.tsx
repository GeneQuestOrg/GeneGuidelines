import type { ReactNode } from "react";
import {
  GuidelinePrsPanel,
  RunsPanel,
  SettingsPanel,
  ToolsPanel,
  WorkflowsWorkspace,
} from "@gene-guidelines/ops";
import type { AdminRoute } from "../router/types";
import { PlaceholderSection } from "./PlaceholderSection";
import { UsersView } from "./UsersView";

export function adminSectionContent(route: AdminRoute): ReactNode {
  switch (route.name) {
    case "runs":
      return <RunsPanel />;
    case "workflows":
      return <WorkflowsWorkspace />;
    case "tools":
      return <ToolsPanel />;
    case "prs":
      return <GuidelinePrsPanel />;
    case "users":
      return <UsersView />;
    case "settings":
      return <SettingsPanel />;
    case "devComponents":
      return (
        <PlaceholderSection
          title="Dev components"
          description="Design system preview — add a lazy DevComponents page when needed."
        />
      );
    default:
      return (
        <PlaceholderSection
          title="Admin"
          description="Select a section from the sidebar."
        />
      );
  }
}
