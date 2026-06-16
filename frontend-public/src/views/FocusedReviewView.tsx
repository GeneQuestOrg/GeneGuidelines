import { useState } from "react";
import { Button } from "@gene-guidelines/ui";
import type { Disease } from "../types/disease";
import type { GuidelineSuggestion, SuggestionComment } from "../types/guidelineSuggestion";
import type { ViewRole } from "../auth/resolveRole";
import { RolePill } from "../components/guidelines/RolePill";
import { GuidelineContextDiff } from "../components/guidelines/GuidelineContextDiff";
import { EvidenceMeter } from "../components/guidelines/EvidenceMeter";
import { CitationRow } from "../components/guidelines/CitationRow";
import { SignalBlock } from "../components/guidelines/SignalBlock";
import { RegenDraft } from "../components/guidelines/RegenDraft";

/**
 * Focused review of one AI suggestion (draft10 `FocusedReview`, /guidelines/pr/:id).
 * Diff-in-context for a modification / placement preview for an addition, plus
 * why-AI, evidence, the rating signal, and a clinician-only comment thread with
 * "regenerate with my note" → a new versioned draft (never a silent overwrite).
 * Clinician-only; the parent path never reaches here.
 */
export interface FocusedReviewViewProps {
  slug: string;
  disease: Disease;
  suggestion: GuidelineSuggestion;
  role: ViewRole;
  onNav: (path: string) => void;
}

export function FocusedReviewView({
  slug,
  disease,
  suggestion,
  role,
  onNav,
}: FocusedReviewViewProps) {
  const held = role === "doctor-unverified";
  const isAddition = suggestion.kind === "addition";
  const [comments, setComments] = useState<readonly SuggestionComment[]>(
    suggestion.comments,
  );
  const [draft, setDraft] = useState("");
  const [regen, setRegen] = useState(false);

  const addNote = () => {
    const text = draft.trim();
    if (text === "") {
      return;
    }
    setComments([
      ...comments,
      { who: "You", tier: role === "researcher" ? "researcher" : "clinician", text },
    ]);
    setDraft("");
  };

  return (
    <section className="page page--gl2">
      <header className="gx-bar">
        <div className="gx-bar__left">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => onNav(`/diseases/${slug}/guidelines`)}
          >
            ← {disease.nameShort}
          </Button>
          <div>
            <span
              className={`gx-kind ${isAddition ? "gx-kind--add" : "gx-kind--mod"} gx-focus__kind`}
            >
              {isAddition ? "+ addition" : "± modification"}
            </span>
            <h1 className="gx-bar__title">{suggestion.title}</h1>
          </div>
        </div>
        <RolePill role={role} />
      </header>

      <div className="gx-diffwrap">
        <div className="gx-disclaim">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8h.01M11 12h1v4h1" />
          </svg>
          <span>
            {isAddition
              ? "This is a proposed addition to the guideline"
              : "This is a proposed change to the current guideline"}
            . Your rating is a <b>signal for the next reviewer</b> — it does not modify the
            official text.
          </span>
        </div>

        <div className="gx-rationale gx-focus__rationale">
          <span className="lbl">Why AI proposes this</span>
          {suggestion.rationale}
        </div>
        <EvidenceMeter level={suggestion.evidence} />

        <div className="gd__caption">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 3v18h18" />
            <path d="m7 14 3-3 3 3 5-5" />
          </svg>
          {isAddition
            ? "Placement preview — where this addition lands in the document."
            : "The change shown as a unified diff against the source document."}
        </div>
        <GuidelineContextDiff slug={slug} suggestion={suggestion} />

        <div className="gx-focus__evlabel">
          {isAddition ? "Evidence for the addition" : "Evidence for the change"}
        </div>
        <div className="gx-cits gx-cits--boxed">
          {suggestion.citations.length > 0 ? (
            suggestion.citations.map((pmid) => <CitationRow key={pmid} pmid={pmid} />)
          ) : (
            <div className="gx-citrow">
              <div className="gx-citrow__t">No citations attached yet.</div>
            </div>
          )}
        </div>

        <div className="gx-focus__signal">
          <SignalBlock sig={suggestion.signal} held={held} />
          <div className="gx-cmt">
            <span className="gx-cmt__vis">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
                <circle cx="12" cy="12" r="2.5" />
              </svg>
              Visible only to other clinicians and researchers
            </span>
            <textarea
              className="gx-cmt__box"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Note for the next reviewer…"
            />
            <div className="gx-cmt__foot">
              <Button
                variant="primary"
                size="sm"
                type="button"
                disabled={draft.trim() === ""}
                onClick={addNote}
              >
                Add note
              </Button>
              {suggestion.regenSeed != null ? (
                <button
                  type="button"
                  className="gx-regen"
                  disabled={draft.trim() === "" || regen}
                  onClick={() => setRegen(true)}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" />
                  </svg>
                  Regenerate with my note
                </button>
              ) : null}
              <span className="gx-cmt__hint">
                Creates a new, explicitly versioned draft — never a silent overwrite.
              </span>
            </div>
          </div>

          {comments.length > 0 ? (
            <div className="gx-thread">
              {comments.map((c, i) => (
                <div key={i} className="gx-thread__i">
                  <span className="gx-thread__av" aria-hidden="true">
                    {c.who === "You" ? "YOU" : "R"}
                  </span>
                  <div className="gx-thread__b">
                    <div className="gx-thread__who">
                      {c.who}
                      <span className="gx-thread__tier">{c.tier}</span>
                    </div>
                    <p className="gx-thread__tx">{c.text}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {regen && suggestion.regenSeed != null ? (
            <RegenDraft seed={suggestion.regenSeed} onDiscard={() => setRegen(false)} />
          ) : null}
        </div>
      </div>
    </section>
  );
}
