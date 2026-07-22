import { useTranslation } from "react-i18next";
import type { GuidelineSuggestion } from "../../types/guidelineSuggestion";
import { pubmedUrl } from "../../utils/guidelineSynthesis";

/**
 * The change shown in context (draft10 `GLContextDiff`). A modification renders
 * its unified diff vs the FULL source document (wizja 04: diff against the full
 * doc, not the lossy synthesis). An addition renders a placement preview — the
 * proposed content + where it lands in the document.
 */
export interface GuidelineContextDiffProps {
  slug: string;
  suggestion: GuidelineSuggestion;
}

function CitationChips({ pmids }: { pmids: readonly string[] }) {
  const { t } = useTranslation("guidelines");
  if (pmids.length === 0) {
    return null;
  }
  return (
    <>
      {pmids.map((pmid) => (
        <a
          key={pmid}
          className="gx-cit"
          href={pubmedUrl(pmid)}
          target="_blank"
          rel="noopener noreferrer"
          title={t("pmidLabel", { pmid })}
        >
          [{pmid}]
        </a>
      ))}
    </>
  );
}

const FILE_ICON = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
  </svg>
);

export function GuidelineContextDiff({ slug, suggestion }: GuidelineContextDiffProps) {
  const { t } = useTranslation("guidelines");
  // Modification with a diff → unified diff against the source document.
  if (suggestion.kind === "modification" && suggestion.diff != null) {
    const { file, hunk, lines } = suggestion.diff;
    return (
      <div className="gx-diff">
        <div className="gx-diff__h">
          <b>{file}</b> {t("unifiedDiffSuffix")}
        </div>
        <div className="gx-diff__hunk">{hunk}</div>
        {lines.map((ln, i) => (
          <div key={i} className={`gx-diff__l gx-diff__l--${ln.t}`}>
            <span className="gx-diff__n">{ln.o ?? ""}</span>
            <span className="gx-diff__n">{ln.n ?? ""}</span>
            <span className="gx-diff__mk">
              {ln.t === "add" ? "+" : ln.t === "del" ? "−" : ""}
            </span>
            <span className="gx-diff__tx">{ln.tx}</span>
          </div>
        ))}
      </div>
    );
  }

  // Addition (or a modification without a structured diff) → placement preview.
  return (
    <div className="gd">
      <div className="gd__bar">
        <span className="gd__file">
          {FILE_ICON}
          {`guidelines/${slug}.md`}
        </span>
        <span className="gd__stat">
          <span className="add">+1</span>
        </span>
      </div>
      <div className="gd__hunk">
        {suggestion.sectionLabel}
        <span className="gd__hunklbl">
          {suggestion.kind === "addition" ? t("proposedAddition") : t("proposedContent")}
        </span>
      </div>
      <div className="gd__row gd__row--add">
        <span className="gd__gut" />
        <span className="gd__gut" />
        <span className="gd__sign" aria-hidden="true">
          +
        </span>
        <div className="gd__line">
          {suggestion.summary} <CitationChips pmids={suggestion.citations} />
        </div>
      </div>
    </div>
  );
}
