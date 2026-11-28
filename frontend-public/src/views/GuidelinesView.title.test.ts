import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { localizedDiseaseName } from "../utils/diseaseName";

/**
 * The guideline page's own heading names the disease the way the disease card above it does: from seo.json where the app has a name in the page's language, the database name otherwise. It said "Fibrous Dysplasia — co mówią wytyczne" under a card reading "Dysplazja włóknista (FD/MAS)". The view loads its data in effects, which a static render does not run, so its wiring is checked in the source and the name in the catalogues.
 */
const source = readFileSync(fileURLToPath(new URL("./GuidelinesView.tsx", import.meta.url)), "utf8");

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("guideline page heading", () => {
  it("takes the disease's name from the same place as the card", () => {
    expect(source).toContain("const diseaseName = localizedDiseaseName(slug, tSeo) ?? disease.name;");
    expect(source).toContain('t("titleWhatGuidelinesSay", { disease: diseaseName })');
    expect(source).toContain('t("titleGuidelines", { disease: diseaseName })');
  });

  it("reads in Polish on the Polish page, and keeps the database name where the app has no other", async () => {
    await i18n.changeLanguage("pl");
    const tSeo = i18n.getFixedT("pl", "seo");
    const t = i18n.getFixedT("pl", "guidelines");
    expect(t("titleWhatGuidelinesSay", { disease: localizedDiseaseName("fd", tSeo) ?? "Fibrous Dysplasia" })).toBe(
      "Dysplazja włóknista (FD/MAS) — co mówią wytyczne",
    );
    expect(localizedDiseaseName("noonan", tSeo)).toBeNull();
  });
});
