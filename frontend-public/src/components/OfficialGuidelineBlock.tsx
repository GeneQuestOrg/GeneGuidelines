import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Badge } from "@gene-guidelines/ui";
import type { OfficialGuideline } from "../types/officialGuideline";
import "./official-guideline-block.css";

export interface OfficialGuidelineBlockProps {
  pointer: OfficialGuideline;
}

function sourceLabel(source: OfficialGuideline["source"], t: TFunction): string {
  switch (source) {
    case "reviewer":
      return t("officialGuidelineBlock.sourceReviewer");
    case "workflow":
      return t("officialGuidelineBlock.sourceWorkflow");
    default:
      return t("officialGuidelineBlock.sourceSeeded");
  }
}

function pubmedUrl(pmid: string): string {
  return `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(pmid)}/`;
}

export function OfficialGuidelineBlock({ pointer }: OfficialGuidelineBlockProps) {
  const { t } = useTranslation("common");
  return (
    <article className="ogb">
      <header className="ogb__head">
        <div className="ogb__eyebrow">
          <span className="ogb__dot" aria-hidden />
          {t("officialGuidelineBlock.eyebrow")}
        </div>
        <Badge variant="ok">{sourceLabel(pointer.source, t)}</Badge>
      </header>
      <h2 className="ogb__title">{pointer.title}</h2>
      <p className="ogb__meta">
        {pointer.authors} · <em>{pointer.journal}</em> · {pointer.year} ·{" "}
        <code>PMID {pointer.pmid}</code>
      </p>
      {pointer.summary ? (
        <p className="ogb__summary">{pointer.summary}</p>
      ) : null}
      <div className="ogb__actions">
        {pointer.url ? (
          <a
            className="ogb__cta"
            href={pointer.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("officialGuidelineBlock.readConsensusPaper")}
          </a>
        ) : null}
        <a
          className="ogb__pubmed"
          href={pubmedUrl(pointer.pmid)}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("officialGuidelineBlock.openOnPubmed")}
        </a>
      </div>
      <p className="ogb__foot">
        {t("officialGuidelineBlock.footBase", { date: pointer.confirmedAt })}
        {pointer.confirmedBy
          ? t("officialGuidelineBlock.footBySuffix", { name: pointer.confirmedBy })
          : ""}
        .
      </p>
    </article>
  );
}
