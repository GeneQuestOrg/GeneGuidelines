import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, describe, expect, it } from "vitest";
import i18n from "../i18n";
import enGuidelines from "../locales/en/guidelines.json";
import plGuidelines from "../locales/pl/guidelines.json";
import type { Disease } from "../types/disease";
import type { SourceDoc } from "../types/sourceDoc";
import { GuidelineParentView, type GuidelineParentViewProps } from "./GuidelineParentView";

/**
 * Medical-honesty guard for the family-facing guideline gate.
 *
 * When a disease has no agreed guideline, the parent gate said "We've prepared an
 * early draft — show it to your doctor". For a disease with no baseline either, that
 * promised something that does not exist. It surfaced when the evidence gate
 * (ADR 005) started withholding an ungrounded synthesis: the page fell back to the
 * gate and offered a draft that was never built.
 *
 * Overclaiming to a parent is the failure mode the whole guideline layer is built to
 * avoid, so the promise must stay conditional on a draft actually existing.
 *
 * Source-level guard: this project has no component-render harness, so it asserts on
 * the render layer and the copy rather than on a mounted tree.
 */
const source = readFileSync(
  fileURLToPath(new URL("./GuidelineParentView.tsx", import.meta.url)),
  "utf8",
);

describe("parent guideline gate honesty", () => {
  it("decides from the baseline whether a draft exists", () => {
    expect(source).toMatch(/const noDraft = baseline == null;/);
  });

  it("never promises a draft when none was built", () => {
    // Both the title and the body must branch; a half-gated pair would pair an
    // honest heading with copy still describing a draft.
    expect(source).toMatch(/noDraft \? t\("gateNoSourcesTitle"\) : t\("gateTitle"\)/);
    expect(source).toMatch(/noDraft\s*\?\s*t\("gateNoSourcesBody"/);
  });

  it("hides the draft's read-state line when there is no draft", () => {
    expect(source).toMatch(/noDraft \? null : \(/);
  });

  it.each([
    ["en", enGuidelines as Record<string, string>],
    ["pl", plGuidelines as Record<string, string>],
  ])("%s copy states the reason without claiming a draft", (_locale, copy) => {
    expect(copy.gateNoSourcesTitle).toBeTruthy();
    expect(copy.gateNoSourcesBody).toBeTruthy();
    // It has to say WHY — that the literature is insufficient — not merely that a
    // guideline is missing, which the reader can already see.
    expect(copy.gateNoSourcesBody).toMatch(/wystarcz|enough/i);
    // And it must not repeat the draft promise this test exists to remove.
    expect(copy.gateNoSourcesBody).not.toMatch(/szkic|draft/i);
  });
});

/**
 * The no-draft gate says what lies below it, and the page renders exactly that: the source shelf when there is one, otherwise only the way to the doctors. It said "Below are the sources we do have" over a page that rendered none.
 */
const noonan: Disease = {
  slug: "noonan",
  name: "Noonan Syndrome",
  nameShort: "Noonan",
  omim: "163950",
  gene: "PTPN11",
  inheritance: "",
  summary: "",
  types: [],
  related: [],
  prevalenceText: "",
  status: "pending",
  statusDate: null,
  aiDraftDate: null,
  openPRs: 0,
  doctorsCount: 0,
  trialsCount: 0,
  coverage: "skeleton",
  accent: "teal",
  listed: true,
};

const doc: SourceDoc = {
  id: "d1",
  role: "Review",
  pmid: "12345678",
  title: "A review of Noonan syndrome",
  authors: "Author A",
  journal: "Some Journal",
  year: 2024,
  scope: "Diagnosis and management.",
  covers: [],
};

function gate(props: Partial<GuidelineParentViewProps> = {}): string {
  return renderToStaticMarkup(
    createElement(GuidelineParentView, {
      disease: noonan,
      synthesis: null,
      suggestions: [],
      baseline: null,
      hasOfficial: false,
      role: "parent",
      docs: [],
      signInAvailable: false,
      onSignIn: () => {},
      onNav: () => {},
      ...props,
    }),
  );
}

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("no-draft gate: what it promises is what renders", () => {
  it("with shelf documents, says the sources are below and renders them, framed as unsummarised", async () => {
    await i18n.changeLanguage("en");
    const html = gate({ docs: [doc] });
    expect(html).toContain(enGuidelines.gateNoSourcesBelowShelf);
    expect(html).toContain('<section class="srcshelf" id="source-shelf">');
    expect(html).toContain("A review of Noonan syndrome");
    expect(html).toContain(enGuidelines.sourceShelfTitleUnsummarised);
    // The parent framing speaks of a summary above, which this page does not have.
    expect(html).not.toContain(enGuidelines.sourceShelfTitleParent);
    expect(html).not.toContain(enGuidelines.sourceShelfLeadParent);
  });

  it("without shelf documents, promises only the doctors and renders no shelf", async () => {
    await i18n.changeLanguage("en");
    const html = gate();
    expect(html).toContain(enGuidelines.gateNoSourcesBelowDoctors);
    expect(html).not.toContain(enGuidelines.gateNoSourcesBelowShelf);
    expect(html).not.toContain("srcshelf");
    expect(html).toContain("Find a specialist");
  });

  it("with a draft, keeps the draft gate and no shelf below it", async () => {
    await i18n.changeLanguage("en");
    const html = gate({ docs: [doc], baseline: { readState: { read: false, note: "x" } } as GuidelineParentViewProps["baseline"] });
    expect(html).not.toContain("srcshelf");
    expect(html).not.toContain(enGuidelines.gateNoSourcesBelowShelf);
  });

  it.each([
    ["en", enGuidelines as Record<string, string>, /below/i, /source/i],
    ["pl", plGuidelines as Record<string, string>, /poniżej/i, /źródł/i],
  ])("%s: the reason promises nothing below, and the doctors-only line names no sources", (_lang, copy, below, sources) => {
    expect(copy.gateNoSourcesBody).not.toMatch(below);
    expect(copy.gateNoSourcesBelowShelf).toMatch(sources);
    expect(copy.gateNoSourcesBelowDoctors).not.toMatch(sources);
    expect(copy.sourceShelfLeadUnsummarised).not.toMatch(/above|powyżej/i);
  });
});
