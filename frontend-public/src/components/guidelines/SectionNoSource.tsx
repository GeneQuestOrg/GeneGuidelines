import { useTranslation } from "react-i18next";

/** Shown in place of a section body when the source shelf covers nothing for it.
 *
 * The five section headings are the same for every disease, but the literature is
 * not: a condition with no surgical treatment has nothing to put under "Indications
 * for surgery". Left to fill the space, the model restates another section. Saying
 * "no source yet" is both truthful and more useful — it points at the gap instead of
 * hiding it behind text that looks sourced.
 */
export function SectionNoSource() {
  const { t } = useTranslation("guidelines");
  return (
    <div className="gx-nosrc">
      <span className="gx-nosrc__tag">{t("sectionNoSourceBadge")}</span>
      <p className="gx-nosrc__body">{t("sectionNoSourceNote")}</p>
    </div>
  );
}
