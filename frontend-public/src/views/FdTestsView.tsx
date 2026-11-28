import { useTranslation } from "react-i18next";
import { PlaceholderView } from "./PlaceholderView";
import { FdTestsSheet } from "../components/FdTestsSheet";
import { DiseaseHeaderForSlug } from "../components/DiseaseHeader";
import { hasTestsSheet } from "../components/diseaseSections";
import "../styles/fd-tests.css";

export interface FdTestsViewProps {
  readonly slug: string;
  readonly onNav: (path: string) => void;
}

/**
 * The "Baseline tests" tab of a disease page (/diseases/fd/tests): the disease card and its tabs, then the printable list of tests. The sheet itself lives in `FdTestsSheet`; printing from here puts only the sheet on paper (fd-tests.css drops the card and the tabs).
 *
 * FD only: the sentences are about fibrous dysplasia, so another slug gets a not-found page rather than a list implying the quotes transfer.
 */
export function FdTestsView({ slug, onNav }: FdTestsViewProps) {
  const { t } = useTranslation("fd-tests");

  if (!hasTestsSheet(slug)) {
    return (
      <PlaceholderView
        title={t("notFoundTitle")}
        description={t("notFoundDesc")}
        primaryAction={{ label: t("notFoundAction"), path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  return (
    <section className="page">
      <FdTestsSheet
        headingLevel="h1"
        place="tests-page"
        before={<DiseaseHeaderForSlug slug={slug} active="tests" />}
      />
    </section>
  );
}
