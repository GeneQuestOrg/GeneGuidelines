/**
 * First-class "this is an AI summary, not an official guideline" disclaimer.
 * Ported from draft10 `SynthDisclaimer` (.gx-synthnote). Shown above both the
 * parent and the clinician projection of the synthesis.
 */
export interface SynthDisclaimerProps {
  text: string;
}

export function SynthDisclaimer({ text }: SynthDisclaimerProps) {
  return (
    <div className="gx-synthnote">
      <svg
        width="16"
        height="16"
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
      <span>{text}</span>
    </div>
  );
}
