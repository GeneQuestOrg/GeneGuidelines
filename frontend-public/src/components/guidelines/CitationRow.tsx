import { pubmedUrl } from "../../utils/guidelineSynthesis";

/**
 * One evidence citation row (draft10 `CitRow`, .gx-citrow). GL-3 has only the
 * PMID — the rich registry (title/authors/journal) lands with the backend
 * (GL-4 CITATIONS). For now we link the PMID straight to PubMed.
 */
export function CitationRow({ pmid }: { pmid: string }) {
  return (
    <div className="gx-citrow">
      <div className="gx-citrow__t">
        PubMed reference
        <div className="gx-citrow__m">Full citation metadata lands with the backend.</div>
      </div>
      <div className="gx-citrow__r">
        <a
          className="gx-pmid"
          href={pubmedUrl(pmid)}
          target="_blank"
          rel="noopener noreferrer"
        >
          PMID {pmid}
        </a>
      </div>
    </div>
  );
}
