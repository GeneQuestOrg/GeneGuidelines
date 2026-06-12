export type AdminSection =
  | "runs"
  | "workflows"
  | "tools"
  | "prs"
  | "users"
  | "settings"
  | "devComponents";

export type AdminRoute =
  | { name: "runs" }
  | { name: "workflows" }
  | { name: "tools" }
  | { name: "prs" }
  | { name: "users" }
  | { name: "settings" }
  | { name: "devComponents" };
