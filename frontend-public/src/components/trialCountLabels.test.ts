import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, describe, expect, it } from "vitest";
import i18n from "../i18n";
import type { Disease } from "../types";
import enCommon from "../locales/en/common.json";
import plCommon from "../locales/pl/common.json";
import enDoctor from "../locales/en/doctor.json";
import plDoctor from "../locales/pl/doctor.json";
import { DiseaseCard } from "./DiseaseCard";

/**
 * A disease's trial count is every trial on record (`trialsCount`, `/api/diseases/{slug}/trials`): 12 for FD on 2026-11-28, of which 3 recruit. The trials browser opens on recruiting ones, so a label next to the record's number must say it counts every status, and a link that carries that number must open the browser on every status.
 */
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
  doctorsCount: 40,
  trialsCount: 12,
  coverage: "full",
  accent: "teal",
  listed: true,
};

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("trial counts say what they count", () => {
  it("the disease card names every status", async () => {
    await i18n.changeLanguage("en");
    expect(renderToStaticMarkup(createElement(DiseaseCard, { disease: fd, onNav: () => {} }))).toContain(
      "<span>12 trials (any status)</span>",
    );
    await i18n.changeLanguage("pl");
    expect(renderToStaticMarkup(createElement(DiseaseCard, { disease: fd, onNav: () => {} }))).toContain(
      "<span>12 badań klinicznych (każdy status)</span>",
    );
  });

  it.each([
    ["en", enCommon.diseaseCard as Record<string, string>, /any status/],
    ["pl", plCommon.diseaseCard as Record<string, string>, /każdy status/],
  ])("%s: every plural form of the card label names every status", (_lang, card, marker) => {
    const forms = Object.entries(card).filter(([key]) => key.startsWith("trials_"));
    expect(forms.length).toBeGreaterThan(0);
    for (const [, text] of forms) {
      expect(text).toMatch(marker);
    }
  });

  it("the clinician view does not title every trial on record as recruiting", () => {
    expect(enDoctor.trialsTitle).not.toMatch(/recruit/i);
    expect(plDoctor.trialsTitle).not.toMatch(/rekrut/i);
  });

  it("the clinician view's 'see all trials (N)' opens the browser on every status", () => {
    const source = readFileSync(fileURLToPath(new URL("./DiseaseTabs.tsx", import.meta.url)), "utf8");
    expect(source).toMatch(/const allTrialsPath = serializeTrialsQuery\(\{\s*\.\.\.parseTrialsQuery\(\{ disease: slug \}\),\s*status: "all",\s*\}\);/);
    expect(source).toMatch(/onClick=\{\(\) => onNav\(allTrialsPath\)\}\s*>\s*\{t\("diseaseTabs\.seeAllTrialsCount", \{ count: trials\.length \}\)\}/);
  });
});
