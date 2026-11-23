/**
 * The generated "What the guideline says about diagnosis – to show your doctor" block of one disease (`GET /api/diseases/{slug}/guideline-points`, backend/guidelines/points/). Served only when at least three points passed the word-for-word quote check and an independent AI verifier; nobody approved it. FD never has one: its page keeps the hand-written block.
 */
export interface GuidelinePoint {
  readonly id: string;
  /** Verbatim English text from the source; the same on every language page. */
  readonly quote: string;
  readonly summaryEn: string;
  readonly summaryPl: string;
  readonly questionEn: string;
  readonly questionPl: string;
  readonly section: string;
  readonly docId: string;
  readonly docTitle: string;
  readonly docYear: string;
  readonly docCitation: string;
  readonly docUrl: string;
  /** A consensus statement or practice guideline ("A"), a GeneReviews chapter ("B") or another review ("C"). */
  readonly docGrade: string;
  readonly licence: string;
  /** The credit the source's terms ask for (GeneReviews), or "". */
  readonly credit: string;
}

export interface GuidelinePoints {
  /** "guideline", "guideline+reviews" or "reviews": only a block resting on guidelines alone says "the guideline". */
  readonly basis: string;
  readonly titleEn: string;
  readonly titlePl: string;
  readonly noticeEn: string;
  readonly noticePl: string;
  readonly sourceEn: string;
  readonly sourcePl: string;
  readonly credits: readonly string[];
  readonly generatedAt: string;
  readonly points: readonly GuidelinePoint[];
}
