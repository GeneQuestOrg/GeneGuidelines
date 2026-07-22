import { useTranslation } from "react-i18next";
import { pubmedUrl } from "../../utils/guidelineSynthesis";

/**
 * One evidence citation row (draft10 `CitRow`, .gx-citrow). GL-3 has only the
 * PMID — the rich registry (title/authors/journal) lands with the backend
 * (GL-4 CITATIONS). For now we link the PMID straight to PubMed.
 */
export function CitationRow({ pmid }: { pmid: string }) {
  const { t } = useTranslation("guidelines");
  return (
    <div className="gx-citrow">
      <div className="gx-citrow__t">
        {t("pubmedReferenceLabel")}
        <div className="gx-citrow__m">{t("fullCitationNote")}</div>
      </div>
      <div className="gx-citrow__r">
        <a
          className="gx-pmid"
          href={pubmedUrl(pmid)}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("pmidLabel", { pmid })}
        </a>
      </div>
    </div>
  );
}
