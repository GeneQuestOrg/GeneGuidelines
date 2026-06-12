import type { AdminSection } from "../router/types";

export interface AdminNavItem {
  section: AdminSection;
  path: string;
  label: string;
  description: string;
}

export const ADMIN_NAV: readonly AdminNavItem[] = [
  {
    section: "runs",
    path: "#/runs",
    label: "Runs",
    description: "Guideline and research pipeline executions",
  },
  {
    section: "workflows",
    path: "#/workflows",
    label: "Workflows",
    description: "Flow editor (React Flow) — migrating from legacy panel",
  },
  {
    section: "tools",
    path: "#/tools",
    label: "Tools",
    description: "MCP catalog and governance",
  },
  {
    section: "prs",
    path: "#/prs",
    label: "Guideline PRs",
    description: "Review queue for living guideline updates",
  },
  {
    section: "catalog",
    path: "#/catalog",
    label: "Catalog",
    description: "Approve diseases launched from public research",
  },
  {
    section: "users",
    path: "#/users",
    label: "Users",
    description: "Accounts and doctor verification",
  },
  {
    section: "settings",
    path: "#/settings",
    label: "Settings",
    description: "Environment and model configuration",
  },
] as const;
