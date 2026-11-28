import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Disease } from "../types";
import type { OfficialGuideline } from "../types/officialGuideline";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import { withCurrentLocale } from "../router/locale";
import { useDisease } from "../hooks/useDisease";
import { useOfficialGuideline } from "../hooks/useOfficialGuideline";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { useGuidelineSynthesis } from "../hooks/useGuidelineSynthesis";
import { localizeInheritance, localizePrevalence } from "../utils/diseaseFacts";
import { formatDataDate } from "../utils/dataFreshness";
import { pubmedArticleUrl } from "../utils/pubmedUrl";
import { hasOfficialGuideline } from "../utils/officialGuideline";
import { localizedDiseaseName } from "../utils/diseaseName";
import {
  FD_TEST_ROW_COUNT,
  diseaseSectionPath,
  diseaseSectionTabs,
  hasGuidelineSummary,
  type DiseaseSectionId,
} from "./diseaseSections";
import { GUIDELINE_PAGE_ANCHORS } from "./parentPageAnchors";
import "../styles/disease-map.css";

/** "Javaid MK, Boyce A, …" → "Javaid"; a trailing block of initials is not part of the surname. */
function firstAuthorSurname(authors: string): string {
  const first = (authors.split(",")[0] ?? "").trim();
  const words = first.split(/\s+/).filter(Boolean);
  if (words.length > 1 && /^[A-Z]{1,3}$/.test(words[words.length - 1])) {
    words.pop();
  }
  return words.join(" ");
}

function GuidelineCitation({ pointer }: { pointer: OfficialGuideline }) {
  const { t } = useTranslation("disease-map");
  const author = firstAuthorSurname(pointer.authors);
  const several = pointer.authors.includes(",") || /et al/i.test(pointer.authors);
  const lead = several
    ? t("factGuidelineCitation", { author, year: pointer.year })
    : `${author} ${pointer.year}`;
  return (
    <>
      {lead}
      {pointer.pmid ? (
        <>
          {" · "}
          <a
            className="dmap-card__ext"
            href={pubmedArticleUrl(pointer.pmid)}
            target="_blank"
            rel="noopener noreferrer"
            title={pointer.title}
          >
            <code>PMID {pointer.pmid}</code>
          </a>
        </>
      ) : null}
    </>
  );
}

export interface DiseaseHeaderProps {
  readonly disease: Disease;
  readonly pointer: OfficialGuideline | null;
  /** Documents on the source shelf; the guideline page lists exactly these. */
  readonly shelfCount: number;
  readonly synthesis: GuidelineSynthesis | null;
  /** True while `synthesis` is still loading: the tab strip is drawn with the tabs known so far, so it does not appear only once the summary's tab is known. */
  readonly summaryLoading?: boolean;
  /** The tab of the page this header sits on; null when that page has no tab (e.g. the guideline page without a summary). */
  readonly active: DiseaseSectionId | null;
  /** `full` on the Start tab (the page's h1, lead and actions); `compact` above another tab's own content, which carries the page's h1. */
  readonly variant: "full" | "compact";
  /** Buttons at the card's lower right (full variant only). */
  readonly actions?: ReactNode;
}

/**
 * The disease card and the tab strip under it, the same on every tab of a disease page (design 1, chosen 2026-11-27). The card names the disease and its hard facts — gene, inheritance, OMIM, the official guideline and the AI summary, with the date it was written and the note that nobody signed it off — and the strip links to the parts of the page that exist for this disease (components/diseaseSections.ts). Every link is a real address: a doctor who receives the summary page from a parent can reach the rest from it.
 */
export function DiseaseHeader({
  disease,
  pointer,
  shelfCount,
  synthesis,
  summaryLoading = false,
  active,
  variant,
  actions,
}: DiseaseHeaderProps) {
  const { t, i18n } = useTranslation("disease-map");
  const { t: tCommon } = useTranslation("common");
  const { t: tSeo } = useTranslation("seo");
  const slug = disease.slug;
  const compact = variant === "compact";
  const summary = hasGuidelineSummary(synthesis);
  const tabs = diseaseSectionTabs(slug, { summary });
  const guidelinesPath = diseaseSectionPath(slug, "guidelines");
  const summaryDate = summary ? formatDataDate(synthesis?.lastUpdated, i18n.language) : null;
  const officialExists = hasOfficialGuideline(disease, pointer);
  const nameShort = (disease.nameShort || "").trim();
  // The name the browser tab shows for this page (seo.json), when the app has one in this language; otherwise the database name.
  const localName = localizedDiseaseName(slug, tSeo);
  const title =
    localName ??
    (nameShort && !disease.name.toLowerCase().includes(nameShort.toLowerCase())
      ? `${disease.name} (${nameShort})`
      : disease.name);
  const eyebrow = disease.prevalenceText
    ? localizePrevalence(disease.prevalenceText, i18n.language)
    : "";

  const tabSub = (id: DiseaseSectionId): string => {
    switch (id) {
      case "tests":
        return t("tabTestsSub", { count: FD_TEST_ROW_COUNT });
      case "guidelines":
        return t("tabGuidelinesSub");
      case "start":
      default:
        return t("tabStartSub");
    }
  };
  const tabLabel = (id: DiseaseSectionId): string =>
    id === "tests" ? t("tabTests") : id === "guidelines" ? t("tabGuidelines") : t("tabStart");

  return (
    <div className={`dmap dmap--embedded dmap-head${compact ? " dmap-head--sub" : ""}`}>
      <nav className="dmap-crumb" aria-label={t("crumbAriaLabel")}>
        <a href={withCurrentLocale("/diseases")}>{t("crumbDiseases")}</a>
        <span className="dmap-crumb__sep" aria-hidden="true">
          /
        </span>
        <span>{localName ?? (nameShort || disease.name)}</span>
      </nav>

      <section className={`dmap-card${compact ? " dmap-card--compact" : ""}`}>
        {!compact && eyebrow ? <p className="dmap-card__eyebrow">{eyebrow}</p> : null}
        {compact ? (
          <p className="dmap-card__title">{title}</p>
        ) : (
          <h1 className="dmap-card__title">{title}</h1>
        )}
        {compact ? null : <p className="dmap-card__lead">{t("cardLead")}</p>}

        <div className="dmap-card__foot">
          <dl className="dmap-card__facts">
            {disease.gene ? (
              <div className="dmap-card__fact">
                <dt>{t("factGene")}</dt>
                <dd>
                  <code>{disease.gene}</code>
                </dd>
              </div>
            ) : null}
            {disease.inheritance ? (
              <div className="dmap-card__fact">
                <dt>{t("factInheritance")}</dt>
                <dd>{localizeInheritance(disease.inheritance, i18n.language)}</dd>
              </div>
            ) : null}
            {disease.omim ? (
              <div className="dmap-card__fact">
                <dt>{t("factOmim")}</dt>
                <dd>
                  <code>{disease.omim}</code>
                </dd>
              </div>
            ) : null}
            {/* The source shelf and the AI summary sit with the guideline fact: under the citation, or as the fact's only content when no official guideline is on record. */}
            {pointer != null || summary ? (
              <div className="dmap-card__fact">
                <dt>{pointer != null ? t("factGuideline") : t("tabGuidelines")}</dt>
                {pointer != null ? (
                  <dd>
                    <GuidelineCitation pointer={pointer} />
                  </dd>
                ) : null}
                {summary ? (
                  <dd className="dmap-card__links">
                    {shelfCount > 0 ? (
                      <a
                        href={withCurrentLocale(`${guidelinesPath}#${GUIDELINE_PAGE_ANCHORS.sourceShelf}`)}
                      >
                        {t("linkShelf", { count: shelfCount })}{" "}
                        <span aria-hidden="true">→</span>
                      </a>
                    ) : null}
                    <a href={withCurrentLocale(guidelinesPath)}>
                      {t("linkSummary")} <span aria-hidden="true">→</span>
                    </a>
                  </dd>
                ) : null}
              </div>
            ) : null}
          </dl>
          {!compact && actions != null ? <div className="dmap-card__actions">{actions}</div> : null}
        </div>
        {/* What the summary is, said where its links are: when it was written, that nobody signed it off, and — with no agreed guideline behind it — that it is an AI draft. The summary page repeats its own disclaimer. */}
        {!compact && summary && (summaryDate != null || !officialExists) ? (
          <p className="dmap-card__note">
            {summaryDate != null ? tCommon("dataAsOf.guideline", { date: summaryDate }) : null}
            {summaryDate != null && !officialExists ? " " : null}
            {!officialExists ? tCommon("synthesisTeaser.subAiDraft") : null}
          </p>
        ) : null}
      </section>

      {/* One tab says nothing a reader can act on, so the strip appears only once there is a second part to go to — or while the summary that may add one is loading, so the page below does not move down when it arrives. */}
      {tabs.length > 1 || summaryLoading ? (
        <nav className="dmap-tabs" aria-label={t("tabsAriaLabel")}>
          {tabs.map((tab) => {
            const current = tab.id === active;
            return (
              <a
                key={tab.id}
                className={`dmap-tab${current ? " is-active" : ""}`}
                href={withCurrentLocale(tab.path)}
                aria-current={current ? "page" : undefined}
              >
                <span className="dmap-tab__label">{tabLabel(tab.id)}</span>
                <span className="dmap-tab__sub">{tabSub(tab.id)}</span>
              </a>
            );
          })}
        </nav>
      ) : null}
    </div>
  );
}

export interface DiseaseHeaderForSlugProps {
  readonly slug: string;
  readonly active: DiseaseSectionId;
}

/** The compact header for a page that loads none of the disease's data itself (the printable list of tests). Renders nothing until the disease is known. */
export function DiseaseHeaderForSlug({ slug, active }: DiseaseHeaderForSlugProps) {
  const { disease } = useDisease(slug);
  const { pointer } = useOfficialGuideline(slug);
  const { docs } = useSourceShelf(slug);
  const { synthesis, loading: synthesisLoading } = useGuidelineSynthesis(slug);
  if (disease == null) {
    return null;
  }
  return (
    <DiseaseHeader
      disease={disease}
      pointer={pointer}
      shelfCount={docs.length}
      synthesis={synthesis}
      summaryLoading={synthesisLoading}
      active={active}
      variant="compact"
    />
  );
}
