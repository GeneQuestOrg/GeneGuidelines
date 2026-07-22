import { useTranslation } from "react-i18next";
import type { SourceDoc } from "../../types/sourceDoc";
import type { SynthesisParagraph } from "../../types/guidelineSynthesis";
import { shortDocLabel } from "../../utils/guidelineSynthesis";

/**
 * Per-claim provenance (clinician view): which source document and section a
 * paragraph comes from, plus a marker where a newer document updates an older
 * one. Ported from draft10 `ProvenanceRow` (.gx-prov2 / .gx-srcmark).
 *
 * The source mark opens the in-app "where do we know this from" detail page
 * (`/guidelines/source/:paraId`, GL-3b ProvenanceDetail).
 */
export interface ProvenanceRowProps {
  slug: string;
  docs: readonly SourceDoc[];
  para: SynthesisParagraph;
  onNav: (path: string) => void;
}

const UPDATE_ICON = (
  <svg
    width="12"
    height="12"
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
);

export function ProvenanceRow({ slug, docs, para, onNav }: ProvenanceRowProps) {
  const { t } = useTranslation("guidelines");
  if (para.source == null) {
    return null;
  }
  const label = shortDocLabel(docs, para.source.doc);

  return (
    <div className="gx-prov2">
      <button
        type="button"
        className="gx-srcmark"
        title={t("provRowBasisTitle", { label, loc: para.source.loc })}
        onClick={() => onNav(`/diseases/${slug}/guidelines/source/${para.id}`)}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
        </svg>
        {label}
      </button>
      {para.update != null ? (
        <span className={`gx-prov2__upd${para.update.supersedes ? " is-super" : ""}`}>
          {UPDATE_ICON}
          {para.update.supersedes
            ? t("provRowUpdatesLabel", { doc: shortDocLabel(docs, para.update.supersedes) })
            : t("provRowRefinedLabel")}{" "}
          · {shortDocLabel(docs, para.update.doc)}
        </span>
      ) : null}
    </div>
  );
}
