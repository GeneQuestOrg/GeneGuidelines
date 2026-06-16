import type { ViewRole } from "../../auth/resolveRole";

/** Honest role indicator (draft10 `RolePill`, .gx-role) — reflects login, not a toggle. */
const ROLE_PILL: Record<ViewRole, readonly [string, string]> = {
  anon: ["gx-role--anon", "Reading as · guest"],
  parent: ["gx-role--parent", "Reading as · parent"],
  doctor: ["gx-role--clin", "Reading as · clinician"],
  "doctor-unverified": ["gx-role--clin", "Clinician · unverified"],
  researcher: ["gx-role--clin", "Reading as · researcher"],
};

export function RolePill({ role }: { role: ViewRole }) {
  const [cls, label] = ROLE_PILL[role];
  return (
    <span className={`gx-role ${cls}`}>
      <span className="d" aria-hidden="true" />
      {label}
    </span>
  );
}
