import { useTranslation } from "react-i18next";
import { Status } from "@gene-guidelines/ui";
import type { ContentPrSummary } from "../types";

export interface DiseaseOpenPrListProps {
  prs: readonly ContentPrSummary[];
  loading: boolean;
  error: string | null;
  diseaseSlug: string;
  onNav: (path: string) => void;
}

export function DiseaseOpenPrList({
  prs,
  loading,
  error,
  diseaseSlug,
  onNav,
}: DiseaseOpenPrListProps) {
  const { t } = useTranslation("common");
  if (loading) {
    return <p className="d-open-prs__empty">{t("diseaseOpenPrList.loading")}</p>;
  }

  if (error != null) {
    return <p className="d-open-prs__empty">{error}</p>;
  }

  if (prs.length === 0) {
    return null;
  }

  return (
    <ul className="d-open-prs">
      {prs.map((pr) => (
        <li key={pr.id}>
          <button
            type="button"
            className="d-open-prs__link"
            onClick={() => onNav(`/diseases/${diseaseSlug}/guidelines/pr/${pr.id}`)}
          >
            <span className="d-open-prs__meta">
              <Status status={pr.status} compact />
              <code>{pr.id}</code>
              <span className="d-open-prs__date">{pr.opened}</span>
            </span>
            <span className="d-open-prs__title">{pr.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
