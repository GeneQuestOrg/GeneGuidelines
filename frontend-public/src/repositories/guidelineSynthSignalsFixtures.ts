import type { SynthSectionSignal } from "../types/guidelineSynthesis";

/**
 * Fixture synthesis signals — ported from draft10 `SYNTH_SIGNAL` (chat 019).
 * Keyed per disease → per section id. Asymmetric (thumbs-up / report-problem);
 * flag notes carry no reviewer names. Placeholder until the rating write-path
 * lands (W4/SIG-2).
 */
// Deliberately empty. These fixtures were the source of what production served:
// "7 found this useful · 3 verified" and flag notes signed "Verified reviewer",
// for sections no clinician had ever voted on. A signal is a count of real votes,
// so there is nothing to seed — not in the database, not here.
const FD_SIGNALS: Readonly<Record<string, SynthSectionSignal>> = {};

const MAS_SIGNALS: Readonly<Record<string, SynthSectionSignal>> = {};

export const SYNTH_SIGNALS: Readonly<
  Record<string, Readonly<Record<string, SynthSectionSignal>>>
> = {
  fd: FD_SIGNALS,
  mas: MAS_SIGNALS,
};
