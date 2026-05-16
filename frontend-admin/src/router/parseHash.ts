import type { AdminRoute } from "./types";

export function parseHash(hash: string): AdminRoute {
  const raw = hash || "#/runs";
  const path = (raw.startsWith("#") ? raw.slice(1) : raw).split("?")[0] || "/";
  const parts = path.split("/").filter(Boolean);

  if (parts.length === 0) {
    return { name: "runs" };
  }

  if (parts[0] === "dev" && parts[1] === "components") {
    return { name: "devComponents" };
  }

  const section = parts[0];
  if (
    section === "runs" ||
    section === "workflows" ||
    section === "tools" ||
    section === "prs" ||
    section === "settings"
  ) {
    return { name: section };
  }

  return { name: "runs" };
}
