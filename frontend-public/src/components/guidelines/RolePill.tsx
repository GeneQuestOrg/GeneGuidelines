import { useTranslation } from "react-i18next";
import type { ViewRole } from "../../auth/resolveRole";

/** Honest role indicator (draft10 `RolePill`, .gx-role) — reflects login, not a toggle. */
const ROLE_PILL: Record<ViewRole, readonly [string, string]> = {
  anon: ["gx-role--anon", "rolePill.guest"],
  parent: ["gx-role--parent", "rolePill.parent"],
  doctor: ["gx-role--clin", "rolePill.clinician"],
  "doctor-unverified": ["gx-role--clin", "rolePill.clinicianUnverified"],
  researcher: ["gx-role--clin", "rolePill.researcher"],
  "researcher-unverified": ["gx-role--clin", "rolePill.researcherUnverified"],
};

export function RolePill({ role }: { role: ViewRole }) {
  const { t } = useTranslation("common");
  const [cls, labelKey] = ROLE_PILL[role];
  return (
    <span className={`gx-role ${cls}`}>
      <span className="d" aria-hidden="true" />
      {t(labelKey)}
    </span>
  );
}
