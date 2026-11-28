import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { trackEvent } from "../utils/analytics";
import { printOnly } from "../utils/printOnly";
import "../styles/fd-tests.css";

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
 * other disease, so callers render the sheet for the `fd` slug alone rather than
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

/** Set on `<html>` while the disease page prints only this sheet (see fd-tests.css). */
export const PRINT_FD_TESTS_CLASS = "print-fd-tests";

export interface FdTestsSheetProps {
  /** `h1` on the standalone /tests page, `h2` when the sheet sits inside the disease page. */
  readonly headingLevel: "h1" | "h2";
  /** Where the print happened, for the parent-test count (`print-fd-tests`). */
  readonly place: "tests-page" | "disease-page";
  /** Shown above the sheet's heading inside its column (the disease card and tabs on /tests); never printed. */
  readonly before?: ReactNode;
}

/**
 * A sheet a parent prints, writes results and dates on by hand, and takes to an
 * appointment. It is an artefact, not an article: one A4 page, and the print
 * stylesheet drops the navigation, the buttons and everything else that only
 * works on screen — but never the source line or the note that the foundation
 * wrote it and the guideline authors did not review it.
 *
 * The disease page keeps a hidden copy for the print button on its card, so Print there prints the sheet alone instead of the whole page.
 */
export function FdTestsSheet({ headingLevel, place, before }: FdTestsSheetProps) {
  const { t } = useTranslation("fd-tests");
  const Heading = headingLevel;

  const print = () => {
    trackEvent("print-fd-tests", { place });
    if (place === "disease-page") {
      printOnly(PRINT_FD_TESTS_CLASS);
    } else {
      window.print();
    }
  };

  return (
    <div className="fdtests">
      {before}
      <header className="fdtests-head">
        <div className="fdtests-eyebrow fdtests-screen">{t("eyebrow")}</div>
        <Heading className="fdtests-title">{t("title")}</Heading>
        <p className="fdtests-lede">{t("lede")}</p>
        <div className="fdtests-actions fdtests-screen">
          <button type="button" className="fdtests-btn fdtests-btn--accent" onClick={print}>
            {t("printCta")}
          </button>
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
  );
}
