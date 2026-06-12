export type AdminSection =
  | "runs"
  | "workflows"
  | "tools"
  | "prs"
  | "catalog"
  | "users"
  | "settings"
  | "devComponents";

export type AdminRoute =
  | { name: "runs" }
  | { name: "workflows" }
  | { name: "tools" }
  | { name: "prs" }
  | { name: "catalog" }
  | { name: "users" }
  | { name: "settings" }
  | { name: "devComponents" };
