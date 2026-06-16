/**
 * 3-state rating control for an AI suggestion (draft10 `RatingButtons`,
 * .gx-rate / .gx-sig). useful / not useful / incorrect. This is a SIGNAL for
 * the next clinician — it does not publish or change anything. In GL-3 the
 * value is local state only; the write-path (weighted ranking) lands in W4/SIG-1.
 */
export type Rating = "useful" | "not" | "wrong";

export interface RatingButtonsProps {
  value: Rating | null;
  onChange: (value: Rating | null) => void;
  /** doctor-unverified: can rate locally, but the signal is held until verified. */
  held?: boolean;
}

export function RatingButtons({ value, onChange, held = false }: RatingButtonsProps) {
  const pick = (v: Rating) => onChange(value === v ? null : v);
  return (
    <div className="gx-rate">
      <button
        type="button"
        className={`gx-sig gx-sig--useful ${value === "useful" ? "on" : ""}`}
        onClick={() => pick("useful")}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M7 10v11M2 10h5v11H2zM7 10l4-7a2 2 0 0 1 3 1.5V8h5a2 2 0 0 1 2 2.3l-1.3 8A2 2 0 0 1 16.7 20H7" />
        </svg>
        Useful
      </button>
      <button
        type="button"
        className={`gx-sig gx-sig--not ${value === "not" ? "on" : ""}`}
        onClick={() => pick("not")}
      >
        Not useful
      </button>
      <button
        type="button"
        className={`gx-sig gx-sig--wrong ${value === "wrong" ? "on" : ""}`}
        onClick={() => pick("wrong")}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
        Incorrect
      </button>
      {held ? <span className="gx-held">held · unverified</span> : null}
    </div>
  );
}
