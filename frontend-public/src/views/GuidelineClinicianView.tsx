import { useMemo, useRef } from "react";
import type { Disease } from "../types/disease";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import type { GuidelineSuggestion } from "../types/guidelineSuggestion";
import { weightedSuggestionScore } from "../types/guidelineSuggestion";
import type { GuidelineBaseline } from "../types/guidelineBaseline";
import type { SourceDoc } from "../types/sourceDoc";
import type { ViewRole } from "../auth/resolveRole";
import type { SynthSignalMap } from "../hooks/useSynthSignals";
import { SourceShelf } from "../components/guidelines/SourceShelf";
import { SynthDisclaimer } from "../components/guidelines/SynthDisclaimer";
import { ProvenanceRow } from "../components/guidelines/ProvenanceRow";
import { SynthSignal } from "../components/guidelines/SynthSignal";
import { SuggestionCard } from "../components/guidelines/SuggestionCard";
import { GuidelineBaselineView } from "../components/guidelines/GuidelineBaselineView";
import {
  citationIndex,
  orderedSynthesisPmids,
  pubmedUrl,
} from "../utils/guidelineSynthesis";

export interface GuidelineClinicianViewProps {
  disease: Disease;
  synthesis: GuidelineSynthesis | null;
  suggestions: readonly GuidelineSuggestion[];
  signals: SynthSignalMap;
  /** Level-(c) AI baseline draft, when no guideline exists (GL-5). */
  baseline: GuidelineBaseline | null;
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
          ratings will count toward the weighted signal that other clinicians see.
        </p>
      </div>
    </div>
  );
}

export function GuidelineClinicianView({
  disease,
  synthesis,
  suggestions,
  signals,
  baseline,
  hasOfficial,
  role,
  docs,
  onNav,
}: GuidelineClinicianViewProps) {
  const orderedPmids = useMemo(
    () => (synthesis != null ? orderedSynthesisPmids(synthesis) : []),
    [synthesis],
  );
  const rankedSuggestions = useMemo(
    () =>
      [...suggestions].sort(
        (a, b) => weightedSuggestionScore(b.signal) - weightedSuggestionScore(a.signal),
      ),
    [suggestions],
  );
  const held = role === "doctor-unverified";
  const isResearcher = role === "researcher";
  const suggZoneRef = useRef<HTMLElement | null>(null);

  const scrollToSuggestions = () => {
    const el = suggZoneRef.current;
    if (el == null) {
      return;
    }
    const y = el.getBoundingClientRect().top + window.scrollY - 80;
    window.scrollTo({ top: y, behavior: "smooth" });
  };

  // Level (c): no synthesis. A clinician/researcher sees the AI-built baseline
  // draft for review (GL-5); without one, a quiet placeholder.
  if (!hasOfficial) {
    return (
      <>
        {held ? <UnverifiedBanner /> : null}
        {baseline != null ? (
          <GuidelineBaselineView
            baseline={baseline}
            diseaseName={disease.name}
            held={held}
          />
        ) : (
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
                No AI baseline has been assembled for this disease yet. For now,{" "}
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
        )}
        {docs.length > 0 ? <SourceShelf docs={docs} /> : null}
      </>
    );
  }

  const doc = synthesis!;
  const suggestionWord =
    rankedSuggestions.length === 1 ? "AI suggestion" : "AI suggestions";

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

      {rankedSuggestions.length > 0 ? (
        <button type="button" className="gx-sugglink" onClick={scrollToSuggestions}>
          <span className="gx-sugglink__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2 2 7l10 5 10-5-10-5z" />
              <path d="m2 17 10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </span>
          <span className="gx-sugglink__tx">
            <b>
              {rankedSuggestions.length} {suggestionWord} beyond all the documents
            </b>{" "}
            — listed separately, at the end. The synthesis below stays a faithful summary of
            the sources.
          </span>
          <span className="gx-sugglink__go">
            Go to suggestions
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 5v14M19 12l-7 7-7-7" />
            </svg>
          </span>
        </button>
      ) : null}

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
                <ProvenanceRow slug={disease.slug} docs={docs} para={p} onNav={onNav} />
              </div>
            ))}
            <SynthSignal signal={signals[sec.id]} held={held} />
          </section>
        ))}

        <SourceShelf docs={docs} />
      </article>

      <section ref={suggZoneRef} className="gx-suggzone">
        <div className="gx-suggzone__head">
          <div>
            <div className="gx-suggzone__tag">
              AI suggestions · {rankedSuggestions.length} · to consider
            </div>
            <h2 className="gx-suggzone__title">AI suggestions — beyond the guideline</h2>
          </div>
        </div>
        <p className="gx-suggzone__lead">
          This is <b>not part of the synthesis</b>. It is the live layer over the official
          sources: new pointers from fresher literature, or proposed changes to a specific
          recommendation — <b>to consider</b>, not to manage a patient from. Your rating is a
          signal for the next clinician; it does not publish or change the synthesis.
        </p>
        {rankedSuggestions.length === 0 ? (
          <div className="gx-empty">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <div>
              <b>No AI suggestions right now.</b>
              <p>
                The literature monitor runs in the background; candidates from new evidence
                appear here when they are worth a look.
              </p>
            </div>
          </div>
        ) : (
          <div className="gx-suggrid">
            {rankedSuggestions.map((s) => (
              <SuggestionCard
                key={s.id}
                slug={disease.slug}
                suggestion={s}
                held={held}
                onNav={onNav}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
