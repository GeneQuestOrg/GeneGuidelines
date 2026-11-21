import { useTranslation } from "react-i18next";
import { Button, Section } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { DiseaseCopy } from "../copy";
import type { UserLocation } from "../router/types";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { SubscriptionUiStatus } from "../utils/diseaseSubscriptionStorage";
import { ParentDiseaseMap } from "./ParentDiseaseMap";
import { PARENT_PAGE_ANCHORS } from "./parentPageAnchors";
import { FdTestsSheet } from "./FdTestsSheet";
import { UnusualCaseContact } from "./UnusualCaseContact";
import { MyCaseCta } from "./MyCaseCta";
import { DiseaseTabs } from "./DiseaseTabs";
import { MachineTranslationNote } from "./MachineTranslationNote";
import { OfficialGuidelineBlock } from "./OfficialGuidelineBlock";
import { SynthesisTeaser } from "./guidelines/SynthesisTeaser";
import { hasOfficialGuideline } from "../utils/officialGuideline";
import "../styles/disease-map.css";
import "../styles/fd-tests.css";

export interface ParentDiseasePageProps {
  readonly disease: Disease;
  readonly copy: DiseaseCopy;
  readonly isClinician: boolean;
  readonly sourceCount: number;
  readonly officialPointer: OfficialGuideline | null;
  readonly related: readonly Disease[];
  readonly relatedLoading: boolean;
  readonly userLoc: UserLocation | null;
  readonly subscriptionStatus: SubscriptionUiStatus;
  readonly onSubscribe: () => void;
  readonly onNav: (path: string) => void;
}

/**
 * The parent view of a disease page, in the order decided on 2026-11-20: the orientation map first, then the printable list of tests (FD only, its rows quote the FD/MAS guideline), then the AI guideline summary one click away behind a single card, then the data hub (doctors, trials, therapies, foundations), and at the very bottom a way to write to the foundation about a case that does not fit.
 *
 * Every disease gets the same order; the FD-only parts (the list, the founder anchors, the questions with quotes) are simply absent elsewhere.
 */
export function ParentDiseasePage({
  disease,
  copy,
  isClinician,
  sourceCount,
  officialPointer,
  related,
  relatedLoading,
  userLoc,
  subscriptionStatus,
  onSubscribe,
  onNav,
}: ParentDiseasePageProps) {
  const { t } = useTranslation("disease-map");
  const slug = disease.slug;
  const isFd = slug === "fd";
  const hasSummary = sourceCount > 0;
  const hasGuideline = hasSummary || officialPointer != null;
  const notifyLabel =
    subscriptionStatus === "confirmed"
      ? copy.notifySubscribedCta
      : subscriptionStatus === "pending"
        ? copy.notifyPendingCta
        : copy.notifyCta;

  return (
    <>
      {disease.coverage === "skeleton" ? (
        <div className="d-hero__notice" role="note">
          <span aria-hidden>⚠️</span>
          <p>
            <b>{copy.skeletonNoticeTitle}</b> {copy.skeletonNoticeBody}
          </p>
        </div>
      ) : null}

      <div className="dmap dmap--embedded">
        <ParentDiseaseMap disease={disease} hasGuideline={hasGuideline} onNav={onNav} />
      </div>
      {/* Renders nothing while case uploads are switched off (config/features.ts). */}
      <MyCaseCta disease={disease} onNav={onNav} />

      {isFd ? (
        <div className="fdtests-embed" id={PARENT_PAGE_ANCHORS.tests}>
          <FdTestsSheet headingLevel="h2" place="disease-page" />
        </div>
      ) : null}

      {hasGuideline ? (
        <Section
          title={t("summaryTitle")}
          sub={t("summarySub")}
          action={
            hasSummary ? (
              <Button
                type="button"
                variant={subscriptionStatus === "confirmed" ? "ghost" : "default"}
                onClick={onSubscribe}
              >
                {notifyLabel}
              </Button>
            ) : undefined
          }
          divider
        >
          {hasSummary ? (
            <SynthesisTeaser
              diseaseName={disease.name}
              sourceCount={sourceCount}
              hasOfficial={hasOfficialGuideline(disease, officialPointer)}
              onOpen={() => onNav(`/diseases/${slug}/guidelines`)}
            />
          ) : officialPointer != null ? (
            <OfficialGuidelineBlock pointer={officialPointer} />
          ) : null}
        </Section>
      ) : null}

      <section className="parent-data" aria-labelledby="parent-data-title">
        <h2 id="parent-data-title" className="parent-data__title">
          {t("dataTitle")}
        </h2>
        <MachineTranslationNote />
        <DiseaseTabs
          disease={disease}
          copy={copy}
          isClinician={isClinician}
          related={related}
          relatedLoading={relatedLoading}
          userLoc={userLoc}
          onNav={onNav}
        />
      </section>

      <div className="dmap dmap--embedded dmap--closing">
        <UnusualCaseContact disease={disease} />
        {/* An invitation to write, not a form: collecting addresses would create
            an obligation the foundation cannot meet yet. */}
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
    </>
  );
}
