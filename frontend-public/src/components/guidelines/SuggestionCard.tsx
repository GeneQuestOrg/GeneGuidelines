import { useState } from "react";
import type { GuidelineSuggestion } from "../../types/guidelineSuggestion";
import { RatingButtons, type Rating } from "./RatingButtons";
import { EVID_LABEL } from "./EvidenceMeter";

/**
 * Rail triage card (draft10 `SuggestionCard`, .gx-tri). Carries only what's
 * needed to triage + rate; clicking the card (anywhere but the rating control)
 * opens the full suggestion view, where the depth lives. Rating stays in the
 * rail — the cheapest signal from a busy clinician who never clicks deeper.
 */
export interface SuggestionCardProps {
  slug: string;
  suggestion: GuidelineSuggestion;
  held?: boolean;
  onNav: (path: string) => void;
}

const ratingWord = (n: number) => (n === 1 ? "rating" : "ratings");

export function SuggestionCard({ slug, suggestion, held = false, onNav }: SuggestionCardProps) {
  const [vote, setVote] = useState<Rating | null>(null);
  const sig = suggestion.signal;
  const open = () => onNav(`/diseases/${slug}/guidelines/pr/${suggestion.id}`);
  const enterLabel =
    suggestion.kind === "addition" ? "Content · placement" : "Diff · evidence · discussion";

  return (
    <div
      className="gx-tri"
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
    >
      <div className="gx-tri__meta">
        <span className={`gx-kind ${suggestion.kind === "addition" ? "gx-kind--add" : "gx-kind--mod"}`}>
          {suggestion.kind === "addition" ? "+ addition" : "± modification"}
        </span>
        <span
          className={`gx-tri__evid gx-tri__evid--${suggestion.evidence}`}
          title={`Evidence strength: ${EVID_LABEL[suggestion.evidence]}`}
        >
          <span className="gx-tri__dot" aria-hidden="true" />
          {EVID_LABEL[suggestion.evidence]}
        </span>
      </div>

      <p className="gx-tri__t">{suggestion.title}</p>
      <span className="gx-tri__where">{suggestion.sectionLabel}</span>

      <div
        className="gx-tri__rate"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        role="presentation"
      >
        <div className="gx-tri__count">
          {sig.ratings > 0 ? (
            <>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M7 10v11M2 10h5v11H2zM7 10l4-7a2 2 0 0 1 3 1.5V8h5a2 2 0 0 1 2 2.3l-1.3 8A2 2 0 0 1 16.7 20H7" />
              </svg>
              <b>{sig.useful}</b> useful · {sig.ratings} {ratingWord(sig.ratings)}
              {sig.verified > 0 ? (
                <span className="gx-tri__ver" title={`${sig.verified} from verified specialists`}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                  {sig.verified}
                </span>
              ) : null}
            </>
          ) : (
            <span className="gx-tri__noratings">No ratings — rate it first</span>
          )}
        </div>
        <RatingButtons value={vote} onChange={setVote} held={held} />
      </div>

      <div className="gx-tri__open">
        <span>{enterLabel}</span>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      </div>
    </div>
  );
}
