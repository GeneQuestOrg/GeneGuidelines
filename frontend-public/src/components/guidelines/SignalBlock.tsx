import { useState } from "react";
import { RatingButtons, type Rating } from "./RatingButtons";
import type { SuggestionSignal } from "../../types/guidelineSuggestion";

/**
 * The rating control + weighted aggregate for a suggestion (draft10
 * `SignalBlock`, .gx-signal / .gx-agg). The rating is a SIGNAL for the next
 * clinician — it does not publish. GL-3: vote is local state; the write-path
 * + weighted ranking land in W4/SIG-1.
 */
export interface SignalBlockProps {
  sig: SuggestionSignal;
  held?: boolean;
}

export function SignalBlock({ sig, held = false }: SignalBlockProps) {
  const [vote, setVote] = useState<Rating | null>(null);
  const total = sig.useful + sig.not + sig.wrong || 1;
  const ratingWord = sig.ratings === 1 ? "rating" : "ratings";

  return (
    <div className="gx-signal">
      <div className="gx-signal__row">
        <span className="gx-signal__q">Your rating:</span>
        <RatingButtons value={vote} onChange={setVote} held={held} />
      </div>
      <div className="gx-agg">
        {sig.ratings > 0 ? (
          <>
            <span className="gx-agg__bar" aria-hidden="true">
              <i className="u" style={{ width: `${(sig.useful / total) * 100}%` }} />
              <i className="n" style={{ width: `${(sig.not / total) * 100}%` }} />
              <i className="w" style={{ width: `${(sig.wrong / total) * 100}%` }} />
            </span>
            <span>
              <b>{sig.ratings}</b> {ratingWord}
              {sig.useful ? ` · ${sig.useful} useful` : ""}
              {sig.wrong ? ` · ${sig.wrong} incorrect` : ""}
            </span>
            {sig.verified > 0 ? (
              <span className="gx-agg__ver">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5z" />
                  <path d="M9 12l2 2 4-4" />
                </svg>
                incl. {sig.verified} from verified specialists
              </span>
            ) : null}
          </>
        ) : (
          <span>No ratings yet — be the first to leave a signal.</span>
        )}
      </div>
    </div>
  );
}
