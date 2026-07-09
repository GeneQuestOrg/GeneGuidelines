import { Button } from "@gene-guidelines/ui";
import type { Disease } from "../types/disease";
import type { GuidelineSynthesis, SynthesisParagraph } from "../types/guidelineSynthesis";
import type { SourceDoc } from "../types/sourceDoc";
import { sourceDocUrl } from "../types/sourceDoc";
import type { ViewRole } from "../auth/resolveRole";
import { RolePill } from "../components/guidelines/RolePill";
import {
  paraphrasesForPmid,
  shortDocLabel,
  pubmedUrl,
} from "../utils/guidelineSynthesis";

/**
 * "Where we know this from" (draft10 `ProvenanceDetail`, /guidelines/source/:paraId).
 * The synthesis claim on the left, the literature it rests on on the right.
 * GL-3b shows the cited PMIDs as the basis; Feature 4 additionally surfaces a
 * grounded PARAPHRASE (our own words, never verbatim) of the passage in the
 * cited abstract that backs the claim — shown only for "supported" claims, with
 * a link to the original on PubMed. Clinician-only.
 */
export interface ProvenanceDetailViewProps {
  slug: string;
  disease: Disease;
  synthesis: GuidelineSynthesis;
  docs: readonly SourceDoc[];
  paraId: string;
  role: ViewRole;
  onNav: (path: string) => void;
}

function findParagraph(
  synthesis: GuidelineSynthesis,
  paraId: string,
): { para: SynthesisParagraph; sectionTitle: string } | null {
  for (const section of synthesis.sections) {
    const para = section.paragraphs.find((p) => p.id === paraId);
    if (para != null) {
      return { para, sectionTitle: section.title };
    }
  }
  return null;
}

export function ProvenanceDetailView({
  slug,
  disease,
  synthesis,
  docs,
  paraId,
  role,
  onNav,
}: ProvenanceDetailViewProps) {
  const found = findParagraph(synthesis, paraId);

  const backToGuideline = (
    <Button
      variant="ghost"
      size="sm"
      type="button"
      onClick={() => onNav(`/diseases/${slug}/guidelines`)}
    >
      ← {disease.nameShort}
    </Button>
  );

  if (found == null) {
    return (
      <section className="page page--gl2">
        <header className="gx-bar">
          <div className="gx-bar__left">{backToGuideline}</div>
          <RolePill role={role} />
        </header>
        <div className="gx-empty">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <div>
            <b>Claim not found.</b>
            <p>This statement is no longer in the synthesis.</p>
          </div>
        </div>
      </section>
    );
  }

  const { para, sectionTitle } = found;
  const srcDoc = para.source != null ? docs.find((d) => d.id === para.source!.doc) : undefined;
  const citations = para.citations ?? [];

  return (
    <section className="page page--gl2">
      <header className="gx-bar">
        <div className="gx-bar__left">
          {backToGuideline}
          <div>
            <span className="gx-bar__ver">Basis · {sectionTitle}</span>
            <h1 className="gx-bar__title">Where we know this from</h1>
          </div>
        </div>
        <RolePill role={role} />
      </header>

      <p className="gx-prov__lead">
        On the left — the claim from the synthesis. On the right — the literature it rests
        on. Where the cited abstract clearly supports the claim, we show a short paraphrase
        of the backing passage in our own words (never a verbatim quote); each links to its
        original on PubMed.
      </p>

      <div className="prov">
        <div className="prov__claim">
          <div className="prov__claimhd">Synthesis claim</div>
          <p className="prov__claimtx">{para.text}</p>
          {para.update != null ? (
            <div className={`prov__upd${para.update.supersedes ? " is-super" : ""}`}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5" />
              </svg>
              {para.update.note}
            </div>
          ) : null}
          {srcDoc != null ? (
            <a
              className="prov__primary"
              href={sourceDocUrl(srcDoc)}
              target="_blank"
              rel="noopener noreferrer"
            >
              Base document: {shortDocLabel(docs, srcDoc.id)} ↗
            </a>
          ) : null}
        </div>

        <div className="prov__basis">
          <div className="prov__basishd">
            {citations.length}{" "}
            {citations.length === 1 ? "basis reference" : "basis references"}
          </div>
          {citations.map((pmid) => {
            const paraphrases = paraphrasesForPmid(para, pmid);
            return (
              <div key={pmid} className="prov__frag">
                <div className="prov__fraghd">
                  <span className="prov__fragsrc">Source reference</span>
                  <a
                    className="gx-pmid"
                    href={pubmedUrl(pmid)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    PMID {pmid}
                  </a>
                </div>
                {paraphrases.length > 0 ? (
                  paraphrases.map((q, i) => (
                    <div key={i} className="prov__para">
                      <span className="prov__paratag">
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                        </svg>
                        In our words — paraphrased, not a quote
                      </span>
                      <p className="prov__paratx">{q.paraphrase}</p>
                      {q.supports !== undefined && q.supports !== "" ? (
                        <p className="prov__parasupports">Backs: {q.supports}</p>
                      ) : null}
                      <a
                        className="prov__paralink"
                        href={pubmedUrl(pmid)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Read the original abstract on PubMed ↗
                      </a>
                    </div>
                  ))
                ) : (
                  <div className="prov__title">Cited in support of this claim.</div>
                )}
              </div>
            );
          })}
          {citations.length === 0 ? (
            <div className="gx-empty">
              <div>
                <b>No references attached yet.</b>
                <p>This claim has no literature basis mapped yet.</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
