export type AdminSection =
  | "runs"
  | "workflows"
  | "tools"
  | "prs"
  | "settings"
  | "devComponents";

export type AdminRoute =
  | { name: "runs" }
  | { name: "workflows" }
  | { name: "tools" }
  | { name: "prs" }
  | { name: "settings" }
  | { name: "devComponents" };
