import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, describe, expect, it } from "vitest";
import i18n from "../i18n";
import type { Disease } from "../types";
import type { GuidelineSynthesis } from "../types/guidelineSynthesis";
import type { OfficialGuideline } from "../types/officialGuideline";
import { DiseaseHeader, type DiseaseHeaderProps } from "./DiseaseHeader";
import { ParentDiseaseMap, type ParentDiseaseMapProps } from "./ParentDiseaseMap";

/**
 * The disease card, its tab strip and the orientation map, rendered as markup. What must hold: the tabs are links to real addresses with the current one marked, a tab appears only for a page that exists, the card's counts and links point where they say, and each of the map's five cards has exactly one button whose number is what its listing opens with.
 */
const fd: Disease = {
  slug: "fd",
  name: "Fibrous Dysplasia",
  nameShort: "FD",
  omim: "174800",
  gene: "GNAS",
  inheritance: "Somatic (not inherited)",
  summary: "",
  types: [],
  related: [],
  prevalenceText: "Rare disease",
  status: "pending",
  statusDate: null,
  aiDraftDate: null,
  openPRs: 0,
  doctorsCount: 33,
  trialsCount: 12,
  coverage: "full",
  accent: "teal",
  listed: true,
};

const noonan: Disease = { ...fd, slug: "noonan", name: "Noonan Syndrome", nameShort: "Noonan" };

const pointer: OfficialGuideline = {
  diseaseSlug: "fd",
  title: "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome",
  authors: "Javaid MK, Boyce A, Appelman-Dijkstra N",
  year: 2019,
  journal: "Orphanet J Rare Dis",
  pmid: "31196103",
  url: "https://pubmed.ncbi.nlm.nih.gov/31196103/",
  summary: "",
  confirmedBy: "",
  confirmedAt: "2026-06-25",
  source: "workflow",
};

const synthesis = { status: "draft", lastUpdated: "2026-09-05" } as GuidelineSynthesis;

function header(props: Partial<DiseaseHeaderProps> = {}): string {
  return renderToStaticMarkup(
    createElement(DiseaseHeader, {
      disease: fd,
      pointer,
      shelfCount: 11,
      synthesis,
      active: "start",
      variant: "full",
      ...props,
    }),
  );
}

function map(props: Partial<ParentDiseaseMapProps> = {}): string {
  return renderToStaticMarkup(
    createElement(ParentDiseaseMap, {
      disease: fd,
      hasGuideline: true,
      hasSummary: true,
      officialOnPage: false,
      doctors: { path: "/doctors?disease=fd", count: 40 },
      trials: { path: "/trials?disease=fd", count: 3 },
      foundationsCount: 3,
      ...props,
    }),
  );
}

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("disease card and tabs", () => {
  it("links every tab to its page and marks the one shown", async () => {
    await i18n.changeLanguage("en");
    const html = header();
    expect(html).toContain('<nav class="dmap-tabs" aria-label="Parts of this disease page">');
    expect(html).toMatch(/<a class="dmap-tab is-active" href="\/diseases\/fd" aria-current="page">/);
    expect(html).toContain('href="/diseases/fd/tests"');
    expect(html).toContain('href="/diseases/fd/guidelines"');
    expect(html).toContain("14 items · to print");
    // No numbering on the tabs: the map numbers its steps, the tabs are not steps.
    expect(html).not.toMatch(/dmap-tab__num/);
  });

  it("names the disease in the page's h1 on the Start tab, and in a paragraph above another tab's content", () => {
    expect(header()).toContain('<h1 class="dmap-card__title">Fibrous dysplasia (FD/MAS)</h1>');
    const compact = header({ variant: "compact", active: "tests" });
    expect(compact).not.toContain("<h1");
    expect(compact).toMatch(/<a class="dmap-tab is-active" href="\/diseases\/fd\/tests" aria-current="page">/);
  });

  it("puts the source shelf and the AI summary next to the guideline fact", () => {
    const html = header();
    expect(html).toContain("Javaid et al. 2019");
    expect(html).toContain('href="https://pubmed.ncbi.nlm.nih.gov/31196103/"');
    expect(html).toContain('href="/diseases/fd/guidelines#source-shelf"');
    expect(html).toContain("Source shelf (11)");
    expect(html).toContain("AI summary");
  });

  it("says next to the summary's links when it was written and that nobody signed it off", () => {
    const html = header();
    expect(html).toContain("This summary was written on");
    expect(html).toContain("Nobody has signed it off.");
    expect(html).not.toContain("AI assembled a draft");
    // With no agreed guideline behind it, the summary is called an AI draft.
    expect(header({ pointer: null })).toContain("AI assembled a draft");
  });

  it("shows no guideline tab, summary link or shelf link without a summary, and no strip with a single tab", () => {
    const html = header({ disease: noonan, synthesis: null, pointer: null });
    expect(html).not.toContain("dmap-tabs");
    expect(html).not.toContain("/guidelines");
    expect(header({ synthesis: { status: "pending" } as GuidelineSynthesis })).not.toContain(
      'href="/diseases/fd/guidelines"',
    );
  });

  it("calls the disease what the browser tab calls it, and uses the database name where the app has no other", async () => {
    await i18n.changeLanguage("pl");
    // FD's page title comes from seo.json (hooks/useDocumentMeta.ts); card and breadcrumb use the same name.
    const pl = header();
    expect(pl).toContain('<h1 class="dmap-card__title">Dysplazja włóknista (FD/MAS)</h1>');
    expect(pl).toMatch(/<span>Dysplazja włóknista \(FD\/MAS\)<\/span><\/nav>/);
    expect(header({ variant: "compact", active: "tests" })).toContain(
      '<p class="dmap-card__title">Dysplazja włóknista (FD/MAS)</p>',
    );
    // No Polish name is invented for a disease that has none.
    const other = header({ disease: noonan });
    expect(other).toContain('<h1 class="dmap-card__title">Noonan Syndrome</h1>');
    expect(other).toMatch(/<span>Noonan<\/span><\/nav>/);
    await i18n.changeLanguage("en");
  });

  it("writes the tabs in Polish on the Polish page", async () => {
    await i18n.changeLanguage("pl");
    const html = header();
    expect(html).toContain("Badania startowe");
    expect(html).toContain("14 pozycji · do wydruku");
    expect(html).toContain("Półka źródeł (11)");
    await i18n.changeLanguage("en");
  });
});

describe("orientation map", () => {
  const cards = (html: string) => html.split('<li class="dmap-mcard"').slice(1);

  it("has five cards with exactly one button each", () => {
    const steps = cards(map());
    expect(steps).toHaveLength(5);
    for (const step of steps) {
      expect(step.match(/<a /g) ?? []).toHaveLength(1);
    }
  });

  it("sends each button where its count was measured", () => {
    const [step1, step2, step3, step4, step5] = cards(map());
    expect(step1).toContain('href="/diseases/fd/tests"');
    expect(step1).toContain('<span class="dmap-nub">14</span>');
    expect(step2).toContain('href="/doctors?disease=fd"');
    expect(step2).toContain('<span class="dmap-nub">40</span>');
    expect(step3).toContain('href="/diseases/fd/guidelines"');
    expect(step4).toContain('href="#disease-foundations"');
    expect(step5).toContain('href="/trials?disease=fd"');
    expect(step5).toContain('<span class="dmap-nub">3</span>');
  });

  it("shows no count before the listing has loaded, and no foundations button without foundations", () => {
    const html = map({
      doctors: { path: "/doctors?disease=fd", count: null },
      foundationsCount: 0,
    });
    const [, step2, , step4] = cards(html);
    expect(step2).not.toContain("dmap-nub");
    expect(step4).not.toContain("<a ");
  });

  it("keeps FD's questions beside the map as closed rows, each with the guideline sentence inside", () => {
    const html = map();
    expect(html).toContain('id="disease-questions"');
    expect(html).toContain("Ask your doctor");
    expect((html.match(/<details class="dmap-ask__row">/g) ?? []).length).toBe(6);
    expect(html).not.toMatch(/<details[^>]* open/);
    expect((html.match(/<q lang="en">/g) ?? []).length).toBe(6);
    expect(html).toContain(
      '<summary class="dmap-ask__sum"><span class="dmap-ask__n">Q1</span><span class="dmap-ask__q">Which of these areas',
    );
  });

  it("points step 1 of a disease without a list of tests at its summary when it has no questions", () => {
    const html = map({ disease: noonan });
    const [step1] = cards(html);
    expect(step1).toContain('href="/diseases/noonan/guidelines"');
    expect(html).not.toContain('id="disease-questions"');
    expect(html).toContain('class="dmap-cols dmap-cols--single"');
  });

  it("points step 1 at the generated questions beside the map once they are in", () => {
    const html = map({ disease: noonan, pointsBlock: pointsBlock() });
    const [step1] = cards(html);
    expect(step1).toContain('href="#disease-questions"');
    expect(html).toContain('id="disease-questions"');
    expect(html).toContain('data-testid="generated-guideline-points"');
    // An empty block is no block: no column, no button to it.
    const empty = map({ disease: noonan, pointsBlock: { ...pointsBlock(), points: [] } });
    expect(empty).not.toContain('id="disease-questions"');
  });

  it("holds the questions column and the buttons in their place while what decides them loads", () => {
    const html = map({ disease: noonan, pointsLoading: true, summaryLoading: true, foundationsCount: null });
    // Two columns from the first paint, the second saying only that it is loading.
    expect(html).toContain('class="dmap-cols"');
    expect(html).toContain('<section class="dmap-col dmap-col--ask dmap-col--pending" aria-busy="true"><p class="dmap-pending">Loading…</p></section>');
    expect(html).not.toContain("Ask your doctor");
    const [step1, , step3, step4] = cards(html);
    for (const step of [step1, step3, step4]) {
      expect(step).toContain('dmap-mcard__btn--pending" aria-hidden="true">');
      expect(step).not.toContain("<a ");
    }
  });

  it("draws the tab strip while the summary loads, and only the tabs already known", () => {
    const html = header({ disease: noonan, synthesis: null, pointer: null, summaryLoading: true });
    expect(html).toContain('<nav class="dmap-tabs"');
    expect(html).toContain('href="/diseases/noonan"');
    expect(html).not.toContain("/guidelines");
  });
});

function pointsBlock(): NonNullable<ParentDiseaseMapProps["pointsBlock"]> {
  return {
    basis: "reviews",
    titleEn: "What reviews say about diagnosis – to show your doctor",
    titlePl: "Co mówią przeglądy o rozpoznaniu – do pokazania lekarzowi",
    noticeEn: "",
    noticePl: "",
    sourceEn: "Quotations are from the sources named under each point.",
    sourcePl: "Cytaty pochodzą ze źródeł podanych przy punktach.",
    credits: [],
    generatedAt: "2026-11-24T00:00:00+00:00",
    points: ["p1", "p2", "p3"].map((id) => ({
      id,
      quote: `Verbatim sentence ${id}.`,
      summaryEn: `Summary ${id}.`,
      summaryPl: `Streszczenie ${id}.`,
      questionEn: `Question ${id}?`,
      questionPl: `Pytanie ${id}?`,
      section: "",
      docId: "NBK1",
      docTitle: "A review",
      docYear: "2024",
      docCitation: "Author A et al., A review",
      docUrl: "https://www.ncbi.nlm.nih.gov/books/NBK1/",
      docGrade: "B",
      licence: "restricted",
      credit: "",
    })),
  };
}
