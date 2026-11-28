import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import fdTests from "../locales/en/fd-tests.json";

/**
 * The parts of a disease that have a page of their own, in the order the tab strip under the disease card shows them. A tab is a link to a real address, so a crawler and a shared link land on the same content a click does.
 *
 * A part gets a tab only when its page has something to show for this disease; a tab that opens an empty or "coming soon" page would be a promise the site cannot keep.
 */
export type DiseaseSectionId = "start" | "tests" | "guidelines";

export interface DiseaseSectionTab {
  readonly id: DiseaseSectionId;
  /** Unprefixed in-app path; the caller adds the language prefix. */
  readonly path: string;
}

/** The only disease with a printable list of tests: its rows quote the FD/MAS guideline and say nothing about any other disease. */
const TESTS_SHEET_SLUGS: ReadonlySet<string> = new Set(["fd"]);

export function hasTestsSheet(slug: string): boolean {
  return TESTS_SHEET_SLUGS.has(slug);
}

/** Rows on the printable list (what its tab and the map's step 1 promise). The catalogue holds exactly the rows the sheet renders, in both languages: FdTestsView.copy.test.ts. */
export const FD_TEST_ROW_COUNT = Object.keys(fdTests.rows).length;

/**
 * Whether the guideline page shows a family the AI summary. The page decides the same way (GuidelinesView: a synthesis that is not `pending`); without one it shows a gate that says no guideline summary is available, which is not a page to send anyone to as "the summary".
 */
export function hasGuidelineSummary(
  synthesis: Pick<GuidelineSynthesis, "status"> | null,
): boolean {
  return synthesis != null && synthesis.status !== "pending";
}

export function diseaseSectionPath(slug: string, id: DiseaseSectionId): string {
  switch (id) {
    case "tests":
      return `/diseases/${slug}/tests`;
    case "guidelines":
      return `/diseases/${slug}/guidelines`;
    case "start":
    default:
      return `/diseases/${slug}`;
  }
}

export interface DiseaseSectionFacts {
  /** True when the guideline page has a summary to show ({@link hasGuidelineSummary}). */
  readonly summary: boolean;
}

export function diseaseSectionTabs(
  slug: string,
  { summary }: DiseaseSectionFacts,
): DiseaseSectionTab[] {
  const ids: DiseaseSectionId[] = ["start"];
  if (hasTestsSheet(slug)) {
    ids.push("tests");
  }
  if (summary) {
    ids.push("guidelines");
  }
  return ids.map((id) => ({ id, path: diseaseSectionPath(slug, id) }));
}
