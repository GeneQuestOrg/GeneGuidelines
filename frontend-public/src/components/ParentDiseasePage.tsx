import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Disease } from "../types";
import type { DiseaseCopy } from "../copy";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { SourceDoc } from "../types/sourceDoc";
import type { SubscriptionUiStatus } from "../utils/diseaseSubscriptionStorage";
import { withCurrentLocale } from "../router/locale";
import { useGuidelineSynthesis } from "../hooks/useGuidelineSynthesis";
import { useDiseaseFoundations } from "../hooks/useDiseaseFoundations";
import { useDiseaseTherapies } from "../hooks/useDiseaseTherapies";
import { useListingLinks } from "../hooks/useListingLinks";
import { useScrollToHash } from "../hooks/useScrollToHash";
import { trackEvent } from "../utils/analytics";
import { printOnly } from "../utils/printOnly";
import { DiseaseHeader } from "./DiseaseHeader";
import { ParentDiseaseMap } from "./ParentDiseaseMap";
import { PARENT_PAGE_ANCHORS } from "./parentPageAnchors";
import { diseaseSectionPath, hasGuidelineSummary, hasTestsSheet } from "./diseaseSections";
import { FdTestsSheet, PRINT_FD_TESTS_CLASS } from "./FdTestsSheet";
import { UnusualCaseContact } from "./UnusualCaseContact";
import { MyCaseCta } from "./MyCaseCta";
import { MachineTranslationNote } from "./MachineTranslationNote";
import { OfficialGuidelineBlock } from "./OfficialGuidelineBlock";
import { FoundationsList } from "./FoundationsList";
import { TherapiesList } from "./TherapiesList";
import { FamilyDoctorMaterials } from "./FamilyDoctorMaterials";
import "../styles/disease-map.css";
import "../styles/fd-tests.css";

export interface ParentDiseasePageProps {
  readonly disease: Disease;
  readonly copy: DiseaseCopy;
  readonly sourceDocs: readonly SourceDoc[];
  readonly officialPointer: OfficialGuideline | null;
  readonly related: readonly Disease[];
  readonly subscriptionStatus: SubscriptionUiStatus;
  readonly onSubscribe: () => void;
  readonly onNav: (path: string) => void;
}

interface MoreSectionProps {
  readonly id: string;
  readonly title: string;
  readonly count: number;
  readonly children: ReactNode;
}

/** A collapsed section below the map: its summary names it and says how many entries it holds; the map's buttons and old links open it by id. */
function MoreSection({ id, title, count, children }: MoreSectionProps) {
  return (
    <details className="dmap-more d-anchor" id={id}>
      <summary className="dmap-more__sum">
        <h2 className="dmap-more__title">
          {title} <span className="dmap-more__count">({count})</span>
        </h2>
      </summary>
      <div className="dmap-more__body">{children}</div>
    </details>
  );
}

/**
 * The Start tab of a disease page for parents and anonymous visitors (design 1, chosen 2026-11-27): the disease card with the tab strip, the orientation map beside the questions for the doctor, then — collapsed, and only when there is something in them — foundations, therapies and the materials for the family doctor, and last the way to write to the foundation about a case that does not fit, next to the note that all of this is a starting point for a conversation with a doctor.
 *
 * Every disease gets the same order; the FD-only parts (the list of tests, the hand-written questions) are simply absent elsewhere. The list of tests has its own tab; the copy kept here, hidden, is what the card's print button puts on paper.
 */
export function ParentDiseasePage({
  disease,
  copy,
  sourceDocs,
  officialPointer,
  related,
  subscriptionStatus,
  onSubscribe,
  onNav,
}: ParentDiseasePageProps) {
  const { t } = useTranslation("disease-map");
  const { t: tCommon } = useTranslation("common");
  const slug = disease.slug;
  const isFd = slug === "fd";
  const withTests = hasTestsSheet(slug);
  const { synthesis } = useGuidelineSynthesis(slug);
  const { foundations, loading: foundationsLoading } = useDiseaseFoundations(slug);
  const { therapies, loading: therapiesLoading } = useDiseaseTherapies(slug);
  const listings = useListingLinks(slug);
  // Old links to #disease-foundations / #disease-therapies open their section once it exists.
  useScrollToHash(!foundationsLoading && !therapiesLoading);

  const hasSources = sourceDocs.length > 0;
  const hasGuideline = hasSources || officialPointer != null;
  const hasSummary = hasGuidelineSummary(synthesis);
  // Without a summary to link to, the official guideline is shown here (as before the redesign).
  const officialOnPage = !hasSummary && officialPointer != null;
  const orientation = copy.orientation;
  const notifyLabel =
    subscriptionStatus === "confirmed"
      ? copy.notifySubscribedCta
      : subscriptionStatus === "pending"
        ? copy.notifyPendingCta
        : copy.notifyCta;

  const printTests = () => {
    trackEvent("print-fd-tests", { place: "disease-page" });
    printOnly(PRINT_FD_TESTS_CLASS);
  };

  const actions =
    hasSources || withTests ? (
      <>
        {hasSources ? (
          <button type="button" className="dmap-btn" onClick={onSubscribe}>
            {notifyLabel}
          </button>
        ) : null}
        {withTests ? (
          <button type="button" className="dmap-btn dmap-btn--accent" onClick={printTests}>
            {t("printTests")}
          </button>
        ) : null}
      </>
    ) : undefined;

  return (
    <>
      <DiseaseHeader
        disease={disease}
        pointer={officialPointer}
        shelfCount={sourceDocs.length}
        synthesis={synthesis}
        active="start"
        variant="full"
        actions={actions}
      />

      {disease.coverage === "skeleton" ? (
        <div className="d-hero__notice dmap-notice" role="note">
          <span aria-hidden>⚠️</span>
          <p>
            <b>{copy.skeletonNoticeTitle}</b> {copy.skeletonNoticeBody}
          </p>
        </div>
      ) : null}

      <div className="dmap dmap--embedded">
        <ParentDiseaseMap
          disease={disease}
          hasGuideline={hasGuideline}
          hasSummary={hasSummary}
          officialOnPage={officialOnPage}
          doctors={listings.doctors}
          trials={listings.trials}
          foundationsCount={foundationsLoading ? null : foundations.length}
        />
      </div>
      {/* Renders nothing while case uploads are switched off (config/features.ts). */}
      <MyCaseCta disease={disease} onNav={onNav} />

      {officialOnPage && officialPointer != null ? (
        <div className="d-anchor dmap-official" id={PARENT_PAGE_ANCHORS.guideline}>
          <OfficialGuidelineBlock pointer={officialPointer} />
        </div>
      ) : null}

      <div className="dmap dmap--embedded dmap-mores">
        {/* Foundation and therapy entries are machine-translated on a translated page. */}
        <MachineTranslationNote />
        {foundations.length > 0 ? (
          <MoreSection
            id={PARENT_PAGE_ANCHORS.foundations}
            title={t("foundationsTitle")}
            count={foundations.length}
          >
            <FoundationsList foundations={foundations} diseaseName={disease.name} />
          </MoreSection>
        ) : null}
        {therapies.length > 0 ? (
          <MoreSection
            id={PARENT_PAGE_ANCHORS.therapies}
            title={t("therapiesTitle")}
            count={therapies.length}
          >
            <p className="d-panel-note">{tCommon("diseaseTabs.therapiesNote")}</p>
            <TherapiesList therapies={therapies} />
          </MoreSection>
        ) : null}
        {orientation != null && hasSources ? (
          <MoreSection
            id={PARENT_PAGE_ANCHORS.familyDoctor}
            title={orientation.familyDoctorTitle}
            count={sourceDocs.length}
          >
            <FamilyDoctorMaterials
              docs={sourceDocs}
              copy={orientation}
              diseaseName={disease.nameShort || disease.name}
              onSeeAll={() => onNav(diseaseSectionPath(slug, "guidelines"))}
              variant="disclosure"
            />
          </MoreSection>
        ) : null}
        {related.length > 0 ? (
          <p className="dmap-related">
            <span className="dmap-related__k">{copy.relatedTitle}:</span>{" "}
            {related.map((d, index) => (
              <span key={d.slug}>
                {index > 0 ? ", " : null}
                <a href={withCurrentLocale(diseaseSectionPath(d.slug, "start"))}>{d.name}</a>
              </span>
            ))}
          </p>
        ) : null}
      </div>

      <div className="dmap dmap--embedded dmap--closing">
        <div className="dmap-closing">
          <UnusualCaseContact disease={disease} />
          <div className="dmap-safety" role="note">
            <span className="dmap-safety__ic" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8h.01M11 12h1v4h1" />
              </svg>
            </span>
            <div className="dmap-safety__b">
              <b>{t("safetyBold")}</b> {t("safetyBody")}
            </div>
          </div>
        </div>
        {/* An invitation to write, not a form: collecting addresses would create an obligation the foundation cannot meet yet. */}
        {isFd ? (
          <p className="dmap-feedback">
            {t("feedbackPart1")}{" "}
            <a href="mailto:kontakt@genequest.org">{t("feedbackEmail")}</a>{" "}
            {t("feedbackPart2")}
          </p>
        ) : null}
        <footer className="dmap-foot">
          <b>GeneGuidelines</b> {t("footerPart1")} <em>{t("footerEm")}</em>
        </footer>
      </div>

      {/* What the card's print button puts on paper: the list of tests, the same sheet as on its own tab. Never shown on screen; fd-tests.css shows it only while that print runs. */}
      {withTests ? (
        <div className="fdtests-embed fdtests-embed--print" aria-hidden="true">
          <FdTestsSheet headingLevel="h2" place="disease-page" />
        </div>
      ) : null}
    </>
  );
}
