import { useTranslation } from "react-i18next";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/fd-tests.css";
import { trackEvent } from "../utils/analytics";

/**
 * The rows of the printable list, in print order.
 *
 * Every row is a test the FD/MAS guideline (Javaid MK et al., Orphanet J Rare Dis
 * 2019;14:139, PMID 31196103) names in the evaluation it prescribes, plus the GNAS
 * row. The copy lives in `locales/{pl,en}/fd-tests.json`; the verbatim sentence
 * behind each row is identical in both languages, because a translated quotation
 * is not a quotation. `FdTestsView.copy.test.ts` holds both rules mechanically.
 *
 * FD only. The sentences are about fibrous dysplasia and say nothing about any
 * other disease, so the list refuses to render for another slug rather than
 * implying the quotes transfer.
 */
const ROW_IDS = [
  "labs",
  "phosphate",
  "wholeBody",
  "radiographs",
  "craniofacialCt",
  "hearing",
  "thyroid",
  "pituitary",
  "testicular",
  "ovarian",
  "growth",
  "adrenal",
  "skin",
  "gnas",
] as const;

export interface FdTestsViewProps {
  readonly slug: string;
  readonly onNav: (path: string) => void;
}

/**
 * A sheet a parent prints, writes results and dates on by hand, and takes to an
 * appointment. It is an artefact, not an article: one A4 page, and the print
 * stylesheet drops the navigation, the buttons and everything else that only
 * works on screen — but never the source line or the note that the foundation
 * wrote it and the guideline authors did not review it.
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
      <div className="fdtests">
        <nav className="fdtests-crumb fdtests-screen" aria-label={t("crumbAriaLabel")}>
          <a href="/diseases" onClick={go("/diseases")}>
            {t("crumbDiseases")}
          </a>
          <span className="fdtests-crumb__sep">/</span>
          <a href="/diseases/fd/map" onClick={go("/diseases/fd/map")}>
            {t("crumbMap")}
          </a>
          <span className="fdtests-crumb__sep">/</span>
          <span>{t("crumbHere")}</span>
        </nav>

        <header className="fdtests-head">
          <div className="fdtests-eyebrow fdtests-screen">{t("eyebrow")}</div>
          <h1 className="fdtests-title">{t("title")}</h1>
          <p className="fdtests-lede">{t("lede")}</p>
          <div className="fdtests-actions fdtests-screen">
            <button
              type="button"
              className="fdtests-btn fdtests-btn--accent"
              onClick={() => {
                trackEvent("print-fd-tests");
                window.print();
              }}
            >
              {t("printCta")}
            </button>
            <a
              className="fdtests-btn"
              href="/diseases/fd/map"
              onClick={go("/diseases/fd/map")}
            >
              {t("backToMap")}
            </a>
          </div>
        </header>

        <table className="fdtests-table">
          <thead>
            <tr>
              <th scope="col">{t("colTest")}</th>
              <th scope="col">{t("colWhy")}</th>
              <th scope="col">{t("colWhen")}</th>
              <th scope="col">{t("colResult")}</th>
            </tr>
          </thead>
          <tbody>
            {ROW_IDS.map((id) => {
              const whenQuote = t(`rows.${id}.whenQuote`, { defaultValue: "" });
              return (
                <tr key={id}>
                  <th scope="row" className="fdtests-name">
                    {t(`rows.${id}.name`)}
                  </th>
                  <td className="fdtests-why">
                    {t(`rows.${id}.why`)}{" "}
                    <span className="fdtests-src">
                      <span className="fdtests-src__lbl">{t("quoteLabel")}</span>{" "}
                      <q>{t(`rows.${id}.quote`)}</q>
                    </span>
                  </td>
                  <td className="fdtests-when">
                    {t(`rows.${id}.when`)}{" "}
                    {whenQuote.length > 0 ? (
                      <span className="fdtests-src">
                        <span className="fdtests-src__lbl">{t("quoteLabel")}</span>{" "}
                        <q>{whenQuote}</q>
                      </span>
                    ) : null}
                  </td>
                  <td className="fdtests-result">
                    <span className="fdtests-rule" aria-hidden />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <footer className="fdtests-foot">
          <p className="fdtests-foot__src">{t("sourceLine")}</p>
          <p>{t("authorshipLine")}</p>
          <p>{t("safetyLine")}</p>
        </footer>
      </div>
    </section>
  );
}
