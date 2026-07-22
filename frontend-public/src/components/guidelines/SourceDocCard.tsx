import { useTranslation } from "react-i18next";
import type { SourceDoc } from "../../types/sourceDoc";
import { sourceDocUrl } from "../../types/sourceDoc";
import "./source-shelf.css";

export interface SourceDocCardProps {
  doc: SourceDoc;
  /** Parent projection: hide clinician-only detail (covers, updates note). */
  parent?: boolean;
}

export function SourceDocCard({ doc, parent = false }: SourceDocCardProps) {
  const { t } = useTranslation("guidelines");
  const url = sourceDocUrl(doc);
  const idLabel = doc.pmid
    ? t("pmidLabel", { pmid: doc.pmid })
    : doc.bookshelf
      ? t("ncbiIdLabel", { bookshelf: doc.bookshelf })
      : "";

  return (
    <article className="srcdoc">
      <div className="srcdoc__head">
        <span className="srcdoc__role">{doc.role}</span>
        {doc.isNew ? <span className="gx-new">{t("newBadge")}</span> : null}
      </div>
      <h4 className="srcdoc__title">{doc.title}</h4>
      <div className="srcdoc__meta">
        {doc.authors} · <em>{doc.journal}</em> · {doc.year}
      </div>
      <p className="srcdoc__scope">{doc.scope}</p>
      {!parent ? (
        <div className="srcdoc__covers">
          {doc.covers.map((cover) => (
            <span key={cover} className="srcdoc__chip">
              {cover}
            </span>
          ))}
        </div>
      ) : null}
      {doc.updatesNote && !parent ? (
        <div className="srcdoc__updates">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5" />
          </svg>
          {doc.updatesNote}
        </div>
      ) : null}
      <div className="srcdoc__foot">
        <a
          className="srcdoc__link"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {doc.bookshelf ? t("openOnNcbi") : t("originalOnPubmed")} ↗
        </a>
        {idLabel ? <code className="srcdoc__id">{idLabel}</code> : null}
      </div>
    </article>
  );
}
