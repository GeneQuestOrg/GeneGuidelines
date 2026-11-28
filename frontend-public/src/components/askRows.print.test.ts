// @vitest-environment jsdom
import { act, createElement, type ReactElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import type { Disease } from "../types";
import type { GuidelinePoints } from "../types/guidelinePoints";
import { GuidelinePointsBlock } from "./GeneratedGuidelinePoints";
import { ParentDiseaseMap } from "./ParentDiseaseMap";

/**
 * The questions for the doctor are collapsed rows on screen — the question is the row's header, the summary and the verbatim sentence open under it — but a parent prints them to take to the appointment, so a print must show every row open. A browser prints a closed `<details>` closed; on `beforeprint` the page opens every closed row and on `afterprint` closes exactly those again. Mounted in a DOM (jsdom) so the events really fire.
 */
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const point = (id: string, question: string) => ({
  id,
  quote: `Verbatim sentence ${id}.`,
  summaryEn: `Summary ${id}.`,
  summaryPl: `Streszczenie ${id}.`,
  questionEn: question,
  questionPl: question,
  section: "",
  docId: "NBK1",
  docTitle: "A review",
  docYear: "2024",
  docCitation: "Author A et al., A review",
  docUrl: "https://www.ncbi.nlm.nih.gov/books/NBK1/",
  docGrade: "B",
  licence: "restricted",
  credit: "",
});

const block: GuidelinePoints = {
  basis: "reviews",
  titleEn: "What reviews say about diagnosis – to show your doctor",
  titlePl: "Co mówią przeglądy o rozpoznaniu – do pokazania lekarzowi",
  noticeEn: "",
  noticePl: "",
  sourceEn: "Quotations are from the sources named under each point.",
  sourcePl: "Cytaty pochodzą ze źródeł podanych przy punktach.",
  credits: [],
  generatedAt: "2026-11-24T00:00:00+00:00",
  points: [point("p1", "First question?"), point("p2", "Second question?"), point("p3", "Third question?")],
};

const fd: Disease = {
  slug: "fd",
  name: "Fibrous Dysplasia",
  nameShort: "FD",
  omim: "174800",
  gene: "GNAS",
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
  coverage: "full",
  accent: "teal",
  listed: true,
};

let root: Root | null = null;

async function mount(element: ReactElement): Promise<HTMLElement> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(element);
  });
  return container;
}

afterEach(async () => {
  await act(async () => {
    root?.unmount();
  });
  root = null;
  document.body.innerHTML = "";
});

const rowsOf = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLDetailsElement>("details.dmap-ask__row"));

describe("question rows", () => {
  it("are closed rows headed by the number and the question, with the summary and the quote inside", async () => {
    await i18n.changeLanguage("en");
    const container = await mount(createElement(GuidelinePointsBlock, { block }));
    const rows = rowsOf(container);
    expect(rows).toHaveLength(3);
    expect(rows.every((row) => !row.open)).toBe(true);
    const summary = rows[1].querySelector("summary");
    expect(summary?.textContent).toBe("Q2Second question?");
    const body = rows[1].querySelector(".dmap-ask__body");
    expect(body?.textContent).toContain("Summary p2.");
    expect(body?.querySelector('q[lang="en"]')?.textContent).toBe("Verbatim sentence p2.");
    expect(body?.querySelector("a")?.getAttribute("href")).toBe("https://www.ncbi.nlm.nih.gov/books/NBK1/");
    // The title, the notes and the source line stay outside the rows, visible without opening anything.
    const notice = container.querySelector(".dmap-ask__notice");
    expect(notice?.closest("details")).toBeNull();
    expect(container.querySelector(".dmap-ask__hd")?.closest("details")).toBeNull();
  });

  it("print open, and close again afterwards except the row the reader had opened", async () => {
    const container = await mount(createElement(GuidelinePointsBlock, { block }));
    const rows = rowsOf(container);
    rows[0].open = true;
    window.dispatchEvent(new Event("beforeprint"));
    expect(rows.every((row) => row.open)).toBe(true);
    window.dispatchEvent(new Event("afterprint"));
    expect(rows.map((row) => row.open)).toEqual([true, false, false]);
  });

  it("print open in FD's hand-written block too", async () => {
    const container = await mount(
      createElement(ParentDiseaseMap, {
        disease: fd,
        hasGuideline: true,
        hasSummary: true,
        officialOnPage: false,
        doctors: { path: "/doctors?disease=fd", count: null },
        trials: { path: "/trials?disease=fd", count: null },
        foundationsCount: null,
      }),
    );
    const rows = rowsOf(container);
    expect(rows).toHaveLength(6);
    expect(rows.every((row) => !row.open)).toBe(true);
    window.dispatchEvent(new Event("beforeprint"));
    expect(rows.every((row) => row.open)).toBe(true);
    window.dispatchEvent(new Event("afterprint"));
    expect(rows.every((row) => !row.open)).toBe(true);
  });
});
