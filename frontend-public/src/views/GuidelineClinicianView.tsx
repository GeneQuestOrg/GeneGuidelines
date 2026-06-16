import { useMemo } from "react";
import type { Disease } from "../types/disease";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import type { SourceDoc } from "../types/sourceDoc";
import type { ViewRole } from "../auth/resolveRole";
import { SourceShelf } from "../components/guidelines/SourceShelf";
import { SynthDisclaimer } from "../components/guidelines/SynthDisclaimer";
import { ProvenanceRow } from "../components/guidelines/ProvenanceRow";
import {
  citationIndex,
  orderedSynthesisPmids,
  pubmedUrl,
} from "../utils/guidelineSynthesis";

export interface GuidelineClinicianViewProps {
  disease: Disease;
  synthesis: GuidelineSynthesis | null;
  hasOfficial: boolean;
  role: ViewRole;
  docs: readonly SourceDoc[];
  onNav: (path: string) => void;
}

/** Pending-verification banner — read everything, signal held (ported .gx-unver). */
function UnverifiedBanner() {
  return (
    <div className="gx-unver">
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
      <div>
        <b>You can read everything — your signal is held for now.</b>
        <p>
          Your account is awaiting verification (ORCID + institution). Once verified, your
          ratings will count toward the weighted signal that other clinicians see. Rating
          arrives in a later slice.
        </p>
      </div>
    </div>
  );
}

export function GuidelineClinicianView({
  disease,
  synthesis,
  hasOfficial,
  role,
  docs,
  onNav,
}: GuidelineClinicianViewProps) {
  const orderedPmids = useMemo(
    () => (synthesis != null ? orderedSynthesisPmids(synthesis) : []),
    [synthesis],
  );
  const held = role === "doctor-unverified";
  const isResearcher = role === "researcher";

  // Level (c): no synthesis. The fully AI-built baseline view lands in a later
  // slice (GL-5/6) — show a clinician-facing placeholder for now.
  if (!hasOfficial) {
    return (
      <>
        {held ? <UnverifiedBanner /> : null}
        <div className="gx-empty">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 2 2 7l10 5 10-5-10-5z" />
            <path d="m2 17 10 5 10-5M2 12l10 5 10-5" />
          </svg>
          <div>
            <b>No agreed guideline for {disease.name} yet.</b>
            <p>
              The AI-built baseline view (assembled from scratch, for review) lands in a
              later slice. For now,{" "}
              <a
                href={`#/diseases/${disease.slug}`}
                onClick={(e) => {
                  e.preventDefault();
                  onNav(`/diseases/${disease.slug}`);
                }}
              >
                return to the disease overview
              </a>
              .
            </p>
          </div>
        </div>
        {docs.length > 0 ? <SourceShelf docs={docs} /> : null}
      </>
    );
  }

  const doc = synthesis!;
  return (
    <>
      {held ? <UnverifiedBanner /> : null}

      {/* Researcher depth ladder: synthesis ⇄ fully AI-built version (GL-6 stub). */}
      {isResearcher ? (
        <div className="gx-modetabs" role="tablist" aria-label="Mode">
          <button type="button" role="tab" aria-selected="true" className="on">
            Synthesis + sources <span>review</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected="false"
            disabled
            title="The fully AI-built version lands in a later slice."
          >
            Full AI version <span>experiment</span>
          </button>
        </div>
      ) : null}

      <SynthDisclaimer text={doc.synthDisclaimer} />

      <article className="gx-doc gx-doc--full">
        {doc.sections.map((sec) => (
          <section key={sec.id} className="gx-sec">
            <h2 className="gx-sec__h">{sec.title}</h2>
            {sec.intro != null ? <p className="gx-sec__intro">{sec.intro}</p> : null}
            {sec.paragraphs.map((p) => (
              <div key={p.id} className="gx-para">
                <p>
                  {p.text}
                  {p.citations?.map((pmid) => (
                    <a
                      key={pmid}
                      className="gx-cit"
                      href={pubmedUrl(pmid)}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`PMID ${pmid}`}
                    >
                      [{citationIndex(orderedPmids, pmid)}]
                    </a>
                  ))}
                </p>
                <ProvenanceRow docs={docs} para={p} />
              </div>
            ))}
          </section>
        ))}

        <SourceShelf docs={docs} />
      </article>
    </>
  );
}
