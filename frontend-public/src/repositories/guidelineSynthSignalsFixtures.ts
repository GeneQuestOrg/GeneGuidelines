import type { SynthSectionSignal } from "../types/guidelineSynthesis";

/**
 * Fixture synthesis signals — ported from draft10 `SYNTH_SIGNAL` (chat 019).
 * Keyed per disease → per section id. Asymmetric (thumbs-up / report-problem);
 * flag notes carry no reviewer names. Placeholder until the rating write-path
 * lands (W4/SIG-2).
 */
const FD_SIGNALS: Readonly<Record<string, SynthSectionSignal>> = {
  diagnosis: { up: 7, flags: 0, verified: 3 },
  histopathology: {
    up: 5,
    flags: 1,
    verified: 2,
    flagNotes: [
      {
        who: "Verified reviewer",
        text: "Add that a negative blood GNAS does NOT rule out FD — a first-contact reader could misread it.",
      },
    ],
  },
  therapy: {
    up: 6,
    flags: 1,
    verified: 3,
    flagNotes: [
      {
        who: "Verified reviewer",
        text: "The denosumab summary is faithful to Gun 2024, but state more clearly that a specialist leads it — not the family doctor.",
      },
    ],
  },
  surgery: { up: 8, flags: 0, verified: 4 },
  monitoring: { up: 4, flags: 0, verified: 2 },
};

const MAS_SIGNALS: Readonly<Record<string, SynthSectionSignal>> = {
  overview: { up: 2, flags: 0, verified: 1 },
};

/** Disease slug → (section id → signal). Empty when none. */
export const SYNTH_SIGNALS: Readonly<
  Record<string, Readonly<Record<string, SynthSectionSignal>>>
> = {
  fd: FD_SIGNALS,
  mas: MAS_SIGNALS,
};
