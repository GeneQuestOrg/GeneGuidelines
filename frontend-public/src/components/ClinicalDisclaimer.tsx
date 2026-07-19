import { useTranslation } from "react-i18next";
import type { AudienceView } from "../router/types";

export interface ClinicalDisclaimerProps {
  view: AudienceView;
}

export function ClinicalDisclaimer({ view }: ClinicalDisclaimerProps) {
  const { t } = useTranslation("common");
  const title = t(`disclaimer.${view}.title`);
  const body = t(`disclaimer.${view}.body`);
  return (
    <aside className="gl__disclaimer" role="note" aria-label={title}>
      <strong>{title}</strong>
      <p>{body}</p>
    </aside>
  );
}
