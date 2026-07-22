import { useTranslation } from "react-i18next";

/**
 * Short note on specialist profiles: scores come from publication metadata, not clinical vetting.
 */
export function SpecialistDisclaimer() {
  const { t } = useTranslation("common");
  return (
    <aside
      className="dprofile__disclaimer"
      role="note"
      aria-label={t("specialistDisclaimer.ariaLabel")}
    >
      <strong>{t("specialistDisclaimer.title")}</strong>
      <p>{t("specialistDisclaimer.body")}</p>
    </aside>
  );
}
