import type { ViewRole } from "./resolveRole";

/** Superadmin-only UI projection override. `"auto"` = normal superadmin (researcher view). */
export type ViewAsRole = "auto" | ViewRole;

export const VIEW_AS_OPTIONS: readonly { value: ViewAsRole; label: string }[] = [
  { value: "auto", label: "Superadmin (default)" },
  { value: "parent", label: "Patient / Family" },
  { value: "doctor", label: "Doctor (verified)" },
  { value: "doctor-unverified", label: "Doctor (unverified)" },
  { value: "researcher", label: "Researcher" },
  { value: "anon", label: "Guest (signed out view)" },
] as const;

const STORAGE_KEY = "gg-view-as";

export function isViewAsRole(value: unknown): value is ViewAsRole {
  return (
    typeof value === "string" &&
    (VIEW_AS_OPTIONS as readonly { value: string }[]).some((o) => o.value === value)
  );
}

export function readViewAs(): ViewAsRole {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw != null && isViewAsRole(raw) ? raw : "auto";
  } catch {
    return "auto";
  }
}

export function writeViewAs(role: ViewAsRole): void {
  try {
    localStorage.setItem(STORAGE_KEY, role);
  } catch {
    // ignore
  }
}
