import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import enAbout from "../locales/en/about.json";
import enCommon from "../locales/en/common.json";
import plCommon from "../locales/pl/common.json";
import plAbout from "../locales/pl/about.json";
import { MY_CASE_ENABLED } from "../config/features";

/**
 * The About page describes how the product works. Two ways that quietly became false:
 *
 * It said the platform "runs on Gemma 4, an open model". Ranking and classification
 * still do — but the guideline summaries a reader is actually looking at are written
 * by a frontier model. The sentence was true when written and describes the wrong
 * thing now, which is the most dangerous kind of stale copy: specific, confident, and
 * about the exact artefact on screen.
 *
 * And it described the case-context panel — including the de-identification pipeline
 * that protects it — while the feature is switched off. A privacy promise about
 * machinery that is not running is worse than no promise.
 */
const source = readFileSync(
  fileURLToPath(new URL("./AboutView.tsx", import.meta.url)),
  "utf8",
);

describe("About page claims", () => {
  it.each([
    ["en", enAbout],
    ["pl", plAbout],
  ])("%s does not claim one open model writes the guidelines", (_locale, copy) => {
    const how = copy.how as { p2Text1: string; p2Bold: string; p2Text2: string };
    const paragraph = [how.p2Text1, how.p2Bold, how.p2Text2].join("");

    // It may name Gemma — that is true of the volume work — but must not present it
    // as what produces the summaries.
    expect(paragraph).toMatch(/frontier|model frontier/i);
    expect(paragraph).not.toMatch(/runs on\s*Gemma 4, an open model/i);
    expect(paragraph).not.toMatch(/Działa na modelu\s*Gemma 4, modelu otwartym/i);
  });

  it("does not describe the case-context panel while it is switched off", () => {
    expect(MY_CASE_ENABLED).toBe(false);
    expect(source).toMatch(/MY_CASE_ENABLED \? \(\s*<section id="privacy"/);
    expect(source).toMatch(/MY_CASE_ENABLED \? \(\s*<li>/);
  });

  it.each([
    ["en", enCommon],
    ["pl", plCommon],
  ])("%s footer promises no de-identification that does not happen", (_locale, copy) => {
    const footer = copy.footer as Record<string, string>;
    const line = [footer.poweredByLead, footer.poweredByModel, footer.poweredByTail].join("");

    // It sat on every page claiming an on-device model de-identifies family documents
    // — describing the case-context feature, which is switched off, and switched off
    // precisely BECAUSE the deployment runs Gemma at a hosted provider outside the EU.
    // The property the promise rested on never held in production.
    expect(line).not.toMatch(/de-identif|odpersonalizowan|leaves the building|opuści budynek/i);
    expect(line).toMatch(/frontier/i);
  });

  it("keeps the disabled copy rather than deleting it", () => {
    // Reversible: turning the feature back on must restore its description, not
    // require someone to rewrite it from memory.
    expect(plAbout.privacy).toBeTruthy();
    expect(plAbout.diseasePage.item7Bold).toBeTruthy();
  });
});
