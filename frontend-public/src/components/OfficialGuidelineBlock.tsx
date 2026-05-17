import { Badge } from "@gene-guidelines/ui";
import type { OfficialGuideline } from "../types/officialGuideline";
import "./official-guideline-block.css";

export interface OfficialGuidelineBlockProps {
  pointer: OfficialGuideline;
}

function sourceLabel(source: OfficialGuideline["source"]): string {
  switch (source) {
    case "reviewer":
      return "Reviewer-confirmed";
    case "workflow":
      return "Auto-discovered (pending review)";
    default:
      return "Seeded";
  }
}

function pubmedUrl(pmid: string): string {
  return `https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(pmid)}/`;
}

export function OfficialGuidelineBlock({ pointer }: OfficialGuidelineBlockProps) {
  return (
    <article className="ogb">
      <header className="ogb__head">
        <div className="ogb__eyebrow">
          <span className="ogb__dot" aria-hidden />
          OFFICIAL GUIDELINES · GROUND TRUTH
        </div>
        <Badge variant="ok">{sourceLabel(pointer.source)}</Badge>
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
            Read the consensus paper →
          </a>
        ) : null}
        <a
          className="ogb__pubmed"
          href={pubmedUrl(pointer.pmid)}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open on PubMed
        </a>
      </div>
      <p className="ogb__foot">
        The AI-maintained living document below is read against this paper.
        Confirmed {pointer.confirmedAt}
        {pointer.confirmedBy ? ` by ${pointer.confirmedBy}` : ""}.
      </p>
    </article>
  );
}
