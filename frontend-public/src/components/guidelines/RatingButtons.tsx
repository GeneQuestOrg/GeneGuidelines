/**
 * 3-state rating control for an AI suggestion (draft10 `RatingButtons`,
 * .gx-rate / .gx-sig). useful / not useful / incorrect. This is a SIGNAL for
 * the next clinician — it does not publish or change anything. In GL-3 the
 * value is local state only; the write-path (weighted ranking) lands in W4/SIG-1.
 *
 * Rendered as a segmented control: three connected buttons sharing one border.
 * "Incorrect" carries no resting color — only the active/pressed state brings
 * a muted amber-red tint, preventing it from reading as a badge/verdict at rest.
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
    <div className="gx-rate" role="group" aria-label="Rate this suggestion">
      <div className="gx-rate__seg">
        <button
          type="button"
          className="gx-sig gx-sig--useful"
          aria-pressed={value === "useful"}
          aria-label="Mark as useful"
          onClick={() => pick("useful")}
        >
          Useful
        </button>
        <button
          type="button"
          className="gx-sig gx-sig--not"
          aria-pressed={value === "not"}
          aria-label="Mark as not useful"
          onClick={() => pick("not")}
        >
          Not useful
        </button>
        <button
          type="button"
          className="gx-sig gx-sig--wrong"
          aria-pressed={value === "wrong"}
          aria-label="Mark as incorrect"
          onClick={() => pick("wrong")}
        >
          Incorrect
        </button>
      </div>
      {held ? <span className="gx-held">held · unverified</span> : null}
    </div>
  );
}
