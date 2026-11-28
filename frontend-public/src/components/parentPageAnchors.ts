/**
 * In-page anchors on the parent disease page (the Start tab). The orientation map's buttons jump to some of them, and links shared before the 2026-11 redesign point at the first three, so those ids keep a target: `tests` sits on step 1 of the map (whose button opens the list of tests), `foundations` and `therapies` on their collapsed sections below the map.
 */
export const PARENT_PAGE_ANCHORS = {
  tests: "disease-tests",
  foundations: "disease-foundations",
  therapies: "disease-therapies",
  questions: "disease-questions",
  guideline: "disease-guideline",
  familyDoctor: "disease-family-doctor",
} as const;

/** In-page anchors on the guideline summary page (/diseases/{slug}/guidelines), the target of the disease card's "Source shelf" link. */
export const GUIDELINE_PAGE_ANCHORS = {
  sourceShelf: "source-shelf",
} as const;
