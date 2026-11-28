import { useRef } from "react";
import { useTranslation } from "react-i18next";
import type { Disease } from "../types";
import { PRE_DIAGNOSIS_INTERVIEW_ENABLED } from "../config/features";
import { withCurrentLocale } from "../router/locale";
import { useGuidelinePoints } from "../hooks/useGuidelinePoints";
import { useOpenDetailsForPrint } from "../hooks/useOpenDetailsForPrint";
import type { ListingLink } from "../hooks/useListingLinks";
import { GeneratedGuidelinePoints } from "./GeneratedGuidelinePoints";
import { PARENT_PAGE_ANCHORS } from "./parentPageAnchors";
import { FD_TEST_ROW_COUNT, diseaseSectionPath, hasTestsSheet } from "./diseaseSections";
import "../styles/disease-map.css";

/**
 * The FD guideline points, in the order a family meets them. Each pair is a question and the verbatim guideline sentence it rests on; the plain-language summary of that sentence (askP<n>) is shown first, so a parent brings the doctor what the guideline says instead of quizzing them.
 */
const ASK_QUESTIONS: ReadonlyArray<readonly [string, string]> = [
  ["askQ1", "askS1"],
  ["askQ2", "askS2"],
  ["askQ3", "askS3"],
  ["askQ4", "askS4"],
  ["askQ5", "askS5"],
  ["askQ6", "askS6"],
];

/** Where a step's one button goes. `href` is an in-app path or an in-page `#anchor`. */
interface StepAction {
  readonly href: string;
  readonly label: string;
  readonly count?: number | null;
  /** In-page target below the map (the arrow points down). */
  readonly below?: boolean;
  readonly onClick?: () => void;
}

interface MapStepProps {
  readonly n: number;
  readonly hook: string;
  readonly title: string;
  readonly action: StepAction | null;
  readonly id?: string;
}

function MapStep({ n, hook, title, action, id }: MapStepProps) {
  return (
    <li className="dmap-mcard" id={id}>
      <span className="dmap-mcard__num" aria-hidden="true">
        {n}
      </span>
      <div className="dmap-mcard__body">
        <p className="dmap-mcard__hook">{hook}</p>
        <h3 className="dmap-mcard__title">{title}</h3>
        {action != null ? (
          <a className="dmap-btn dmap-mcard__btn" href={action.href} onClick={action.onClick}>
            {action.label}
            {action.count != null && action.count > 0 ? (
              <span className="dmap-nub">{action.count}</span>
            ) : null}
            <span className="dmap-btn__arr" aria-hidden="true">
              {action.below ? "↓" : "→"}
            </span>
          </a>
        ) : null}
      </div>
    </li>
  );
}

/** Open a collapsed section before the browser scrolls to it (a link to the fragment the address already has fires no hashchange). */
function openSection(id: string): () => void {
  return () => {
    const target = document.getElementById(id);
    if (target instanceof HTMLDetailsElement) {
      target.open = true;
    }
  };
}

export interface ParentDiseaseMapProps {
  readonly disease: Disease;
  /** True when the disease has a source shelf or an official guideline pointer (step 3's wording). */
  readonly hasGuideline: boolean;
  /** True when the guideline page shows an AI summary (components/diseaseSections.ts). */
  readonly hasSummary: boolean;
  /** True when the official guideline is shown on this page because there is no summary to link to. */
  readonly officialOnPage: boolean;
  readonly doctors: ListingLink;
  readonly trials: ListingLink;
  /** Foundations listed in their section below the map; null while loading, 0 when none (no section, no button). */
  readonly foundationsCount: number | null;
}

/**
 * The Start tab's two columns (design 1, chosen 2026-11-27): the orientation map — five compact cards whose step heading carries the "you did not know this exists" message and whose one button each is the page's menu — and, beside it, the questions to take to the doctor.
 *
 * The questions are FD's hand-written block (each with the verbatim FD/MAS guideline sentence behind it) or, for every other disease, the block the guideline-points loop generated and checked. On a phone the questions follow the map.
 */
export function ParentDiseaseMap({
  disease,
  hasGuideline,
  hasSummary,
  officialOnPage,
  doctors,
  trials,
  foundationsCount,
}: ParentDiseaseMapProps) {
  const { t } = useTranslation("disease-map");
  const slug = disease.slug;
  const isFd = slug === "fd";
  const nameShort = disease.nameShort || disease.name;
  const pointsBlock = useGuidelinePoints(slug, !isFd);
  const askColumn = useRef<HTMLElement>(null);
  useOpenDetailsForPrint(askColumn);
  const hasQuestions = isFd || pointsBlock != null;
  const guidelinesPath = withCurrentLocale(diseaseSectionPath(slug, "guidelines"));

  // Step 1 leads to what settles a diagnosis: FD's list of tests; elsewhere the questions beside the map, or the summary when there are none.
  const step1: StepAction | null = hasTestsSheet(slug)
    ? {
        href: withCurrentLocale(diseaseSectionPath(slug, "tests")),
        label: t("tabTests"),
        count: FD_TEST_ROW_COUNT,
      }
    : hasQuestions
      ? { href: `#${PARENT_PAGE_ANCHORS.questions}`, label: t("step1CtaQuestions") }
      : hasSummary
        ? { href: guidelinesPath, label: t("step1CtaConfirm") }
        : null;

  const step3: StepAction = hasSummary
    ? { href: guidelinesPath, label: t("tabGuidelines") }
    : officialOnPage
      ? { href: `#${PARENT_PAGE_ANCHORS.guideline}`, label: t("step3CtaOfficial"), below: true }
      : { href: guidelinesPath, label: t("step3CtaSeeFar") };

  const step4: StepAction | null =
    foundationsCount != null && foundationsCount > 0
      ? {
          href: `#${PARENT_PAGE_ANCHORS.foundations}`,
          label: t("step4Cta"),
          count: foundationsCount,
          below: true,
          onClick: openSection(PARENT_PAGE_ANCHORS.foundations),
        }
      : null;

  return (
    <div className={`dmap-cols${hasQuestions ? "" : " dmap-cols--single"}`}>
      <section className="dmap-col" aria-labelledby="dmap-map-title">
        <p className="dmap-kicker">{t("introKicker")}</p>
        <h2 id="dmap-map-title" className="dmap-h2">
          {t("introTitle")}
        </h2>
        <ol className="dmap-mcards">
          {/* PRE_DIAGNOSIS_INTERVIEW_ENABLED: a planned, unbuilt module; hidden until it exists (see features.ts). */}
          {PRE_DIAGNOSIS_INTERVIEW_ENABLED ? (
            <li className="dmap-mcard">
              <span className="dmap-mcard__num" aria-hidden="true">
                0
              </span>
              <div className="dmap-mcard__body">
                <p className="dmap-mcard__hook">{t("step0Hook")}</p>
                <h3 className="dmap-mcard__title">{t("step0Title")}</h3>
                <div className="dmap-predx">
                  <span className="dmap-predx__tag">{t("step0Tag")}</span>
                  <h4 className="dmap-predx__title">{t("step0PredxTitle")}</h4>
                  <p className="dmap-predx__lede">
                    {t("step0PredxLedePart1")} <b>{t("step0PredxLedeBold1")}</b>
                    {t("step0PredxLedePart2")} <b>{t("step0PredxLedeBold2")}</b>{" "}
                    {t("step0PredxLedePart3")}
                  </p>
                </div>
              </div>
            </li>
          ) : null}
          {/* Step 1 keeps the id the embedded list of tests had, so an old link to it lands on the step that opens the list. */}
          <MapStep
            n={1}
            id={isFd ? PARENT_PAGE_ANCHORS.tests : undefined}
            hook={t("step1Hook")}
            title={t("step1Title")}
            action={step1}
          />
          <MapStep
            n={2}
            hook={t("step2Hook")}
            title={t("step2Title", { name: nameShort })}
            action={{
              href: withCurrentLocale(doctors.path),
              label: t("step2CtaFind", { name: nameShort }),
              count: doctors.count,
            }}
          />
          <MapStep
            n={3}
            hook={hasGuideline ? t("step3HookExists") : t("step3HookAssembling")}
            title={
              hasGuideline
                ? t("step3TitleExists", { name: nameShort })
                : t("step3TitleAssembling", { name: nameShort })
            }
            action={step3}
          />
          <MapStep n={4} hook={t("step4Hook")} title={t("step4Title")} action={step4} />
          <MapStep
            n={5}
            hook={t("step5Hook")}
            title={t("step5Title")}
            action={{
              href: withCurrentLocale(trials.path),
              label: t("step5CtaTrials"),
              count: trials.count,
            }}
          />
        </ol>
      </section>

      {hasQuestions ? (
        <section
          ref={askColumn}
          className="dmap-col dmap-col--ask d-anchor"
          id={PARENT_PAGE_ANCHORS.questions}
          aria-labelledby="dmap-ask-title"
        >
          <p className="dmap-kicker">{t("askKicker")}</p>
          <h2 id="dmap-ask-title" className="dmap-h2">
            {t("askHeading")}
          </h2>
          {/* What the guideline says, to show the doctor — never advice. Each point summarises a verbatim guideline sentence, which sits underneath, and ends in one open question. The framing is deliberate: our own diagnosis went wrong not because a doctor was careless but because one fact (tissue for GNAS) was missing, so the parent brings the fact with the guideline's authority instead of questioning the doctor. Hand-written for FD only — the sentences are from the FD/MAS guideline (Javaid 2019) and say nothing about any other disease. */}
          {isFd ? (
            <div className="dmap-ask">
              <div className="dmap-ask__hd">{t("askTitle")}</div>
              <p className="dmap-ask__note">{t("askNote")}</p>
              {/* One collapsed row per point: the question is the header; opening it shows the summary and the guideline sentence. Printing opens every row (useOpenDetailsForPrint on the column). */}
              <ol className="dmap-ask__list">
                {ASK_QUESTIONS.map(([qKey, sKey], index) => (
                  <li key={qKey} className="dmap-ask__item">
                    <details className="dmap-ask__row">
                      <summary className="dmap-ask__sum">
                        <span className="dmap-ask__n">{t("askNumber", { n: index + 1 })}</span>
                        <span className="dmap-ask__q">{t(qKey)}</span>
                      </summary>
                      <div className="dmap-ask__body">
                        <p className="dmap-ask__point">{t(qKey.replace("askQ", "askP"))}</p>
                        <p className="dmap-ask__lbl">{t("askQuoteLabel")}</p>
                        <p className="dmap-ask__s">
                          {/* The quotation is English on every page; lang lets a screen reader pronounce it as English. */}
                          <q lang="en">{t(sKey)}</q>
                        </p>
                      </div>
                    </details>
                  </li>
                ))}
              </ol>
              <p className="dmap-ask__src">{t("askSource")}</p>
            </div>
          ) : (
            // Every other disease shows the block the guideline-points loop generated and checked (backend/guidelines/points/), or nothing when none was published. FD keeps the hand-written block above, which is also the generator's worked example.
            <GeneratedGuidelinePoints slug={slug} />
          )}
        </section>
      ) : null}
    </div>
  );
}
