import type { SourceDoc } from "../../types/sourceDoc";
import { sourceDocUrl } from "../../types/sourceDoc";
import type { SynthesisParagraph } from "../../types/guidelineSynthesis";
import { shortDocLabel } from "../../utils/guidelineSynthesis";

/**
 * Per-claim provenance (clinician view): which source document and section a
 * paragraph comes from, plus a marker where a newer document updates an older
 * one. Ported from draft10 `ProvenanceRow` (.gx-prov2 / .gx-srcmark).
 *
 * GL-2 placeholder: the source mark links out to the original document. GL-3
 * upgrades it to the in-app "where do we know this from" detail page
 * (`/guidelines/source/:paraId`, ProvenanceDetail + SOURCE_BASIS).
 */
export interface ProvenanceRowProps {
  docs: readonly SourceDoc[];
  para: SynthesisParagraph;
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

export function ProvenanceRow({ docs, para }: ProvenanceRowProps) {
  if (para.source == null) {
    return null;
  }
  const sourceDoc = docs.find((d) => d.id === para.source!.doc);
  const label = shortDocLabel(docs, para.source.doc);
  const href = sourceDoc != null ? sourceDocUrl(sourceDoc) : null;
  const title = `Basis: ${label} · ${para.source.loc} — open the source`;

  const icon = (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );

  return (
    <div className="gx-prov2">
      {href != null ? (
        <a
          className="gx-srcmark"
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          title={title}
        >
          {icon}
          {label}
        </a>
      ) : (
        <span className="gx-srcmark" title={`Basis: ${label} · ${para.source.loc}`}>
          {icon}
          {label}
        </span>
      )}
      {para.update != null ? (
        <span className={`gx-prov2__upd${para.update.supersedes ? " is-super" : ""}`}>
          {UPDATE_ICON}
          {para.update.supersedes
            ? `Updates ${shortDocLabel(docs, para.update.supersedes)}`
            : "Refined"}{" "}
          · {shortDocLabel(docs, para.update.doc)}
        </span>
      ) : null}
    </div>
  );
}
