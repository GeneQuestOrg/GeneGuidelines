import { useTranslation } from "react-i18next";
import { PlaceholderView } from "./PlaceholderView";
import { FdTestsSheet } from "../components/FdTestsSheet";
import "../styles/fd-tests.css";

export interface FdTestsViewProps {
  readonly slug: string;
  readonly onNav: (path: string) => void;
}

/**
 * The printable list of tests on a page of its own (/diseases/fd/tests), for links shared before the list moved onto the disease page. The sheet itself lives in `FdTestsSheet`.
 *
 * FD only: the sentences are about fibrous dysplasia, so another slug gets a not-found page rather than a list implying the quotes transfer.
 */
export function FdTestsView({ slug, onNav }: FdTestsViewProps) {
  const { t } = useTranslation("fd-tests");

  if (slug !== "fd") {
    return (
      <PlaceholderView
        title={t("notFoundTitle")}
        description={t("notFoundDesc")}
        primaryAction={{ label: t("notFoundAction"), path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  const go = (path: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    onNav(path);
  };

  return (
    <section className="page">
      <FdTestsSheet
        headingLevel="h1"
        place="tests-page"
        before={
          <nav className="fdtests-crumb fdtests-screen" aria-label={t("crumbAriaLabel")}>
            <a href="/diseases" onClick={go("/diseases")}>
              {t("crumbDiseases")}
            </a>
            <span className="fdtests-crumb__sep">/</span>
            <a href="/diseases/fd" onClick={go("/diseases/fd")}>
              {t("crumbMap")}
            </a>
            <span className="fdtests-crumb__sep">/</span>
            <span>{t("crumbHere")}</span>
          </nav>
        }
        extraActions={
          <a className="fdtests-btn" href="/diseases/fd" onClick={go("/diseases/fd")}>
            {t("backToMap")}
          </a>
        }
      />
    </section>
  );
}
