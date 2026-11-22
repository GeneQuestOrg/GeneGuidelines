import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, describe, expect, it } from "vitest";
import i18n from "../i18n";
import enPrivacy from "../locales/en/privacy.json";
import plPrivacy from "../locales/pl/privacy.json";
import enSeo from "../locales/en/seo.json";
import plSeo from "../locales/pl/seo.json";
import { PRIVACY_POLICY_VERSION, inlineTokens } from "../content/privacyPolicy.mjs";
import { AppFooter } from "../components/AppFooter";
import { AiInputNotice } from "../components/AiInputNotice";
import { DoctorPrivacyRequest } from "../components/DoctorPrivacyRequest";
import { PrivacyView } from "./PrivacyView";

/**
 * The privacy policy is legal text: the Polish version binds, the English one translates it. What must hold on screen is that the right language shows at the right address, that the date is the published one and never the draft's placeholder, and that a reader can reach the page from every page and from the fields whose text an AI model reads.
 */
async function render(locale: "en" | "pl", element: Parameters<typeof renderToStaticMarkup>[0]) {
  await i18n.changeLanguage(locale);
  return renderToStaticMarkup(element);
}

const view = () => createElement(PrivacyView, { onSetLocale: () => {} });

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("PrivacyView", () => {
  it("shows the binding Polish text on the Polish page, dated", async () => {
    const html = await render("pl", view());
    expect(html).toContain("Polityka prywatności serwisu GeneGuidelines</h1>");
    expect(html).toContain("V. Lekarze w katalogu (informacja z art. 14 RODO)</h2>");
    expect(html).toContain(`<time dateTime="${PRIVACY_POLICY_VERSION}">22 listopada 2026</time>`);
    expect(html).not.toContain("[data publikacji]");
    expect(html).not.toContain("{{date}}");
    // A link across to the translation, for an English reader who landed here.
    expect(html).toContain('href="/privacy"');
  });

  it("shows the English translation, says the Polish one prevails and links to it", async () => {
    const html = await render("en", view());
    expect(html).toContain("GeneGuidelines privacy policy</h1>");
    expect(html).toContain("V. Clinicians in the directory (information under Art. 14 GDPR)</h2>");
    expect(html).toContain(`<time dateTime="${PRIVACY_POLICY_VERSION}">22 November 2026</time>`);
    expect(html).not.toContain("[publication date]");
    expect(html).toContain("the Polish version is legally binding");
    expect(html).toMatch(
      /<a [^>]*href="\/pl\/privacy"[^>]*>Read the Polish version, which is legally binding<\/a>/,
    );
  });

  it.each(["en", "pl"] as const)(
    "%s marks up storage keys and makes the email a link",
    async (locale) => {
      const html = await render(locale, view());
      expect(html).toContain("<code>gg.locale</code>");
      expect(html).toContain("<code>gg-anon-session</code>");
      expect(html).toContain('href="mailto:kontakt@genequest.org"');
      // No Markdown left over from the source document.
      expect(html).not.toContain("**");
      expect(html).not.toContain("`");
    },
  );

  it("renders every section of both versions under the same ids", async () => {
    const plHtml = await render("pl", view());
    const enHtml = await render("en", view());
    const ids = plPrivacy.policy.sections.map((section) => section.id);
    expect(enPrivacy.policy.sections.map((section) => section.id)).toEqual(ids);
    for (const id of ids) {
      expect(plHtml).toContain(`id="${id}"`);
      expect(enHtml).toContain(`id="${id}"`);
    }
  });

  it("has a title and description for the document head in both languages", () => {
    expect(enSeo.privacy.title).toBe("Privacy policy");
    expect(plSeo.privacy.title).toBe("Polityka prywatności");
    expect(enSeo.privacy.description.length).toBeGreaterThan(50);
    expect(plSeo.privacy.description.length).toBeGreaterThan(50);
  });
});

describe("policy inline markup", () => {
  it("splits bold, code and email and keeps everything else as text", () => {
    expect(inlineTokens("**Mapy** ładowane (`gg-tweaks`): kontakt@genequest.org.")).toEqual([
      { kind: "bold", value: "Mapy" },
      { kind: "text", value: " ładowane (" },
      { kind: "code", value: "gg-tweaks" },
      { kind: "text", value: "): " },
      { kind: "email", value: "kontakt@genequest.org" },
      { kind: "text", value: "." },
    ]);
  });
});

describe("links to the policy", () => {
  it.each([
    ["en", "Privacy policy"],
    ["pl", "Polityka prywatności"],
  ] as const)("%s footer links to it on every page", async (locale, label) => {
    const html = await render(locale, createElement(AppFooter, { onNav: () => {} }));
    expect(html).toContain(`<a href="/privacy">${label}</a>`);
  });

  it.each([
    ["en", "/privacy#clinicians"],
    ["pl", "/pl/privacy#clinicians"],
  ] as const)(
    "%s clinician request form points at the clinicians' section",
    async (locale, href) => {
      const html = await render(locale, createElement(DoctorPrivacyRequest, { slug: "jane-doe" }));
      expect(html).toContain(`href="${href}"`);
    },
  );

  it.each([
    ["en", "/privacy", "the text goes to an AI model"],
    ["pl", "/pl/privacy", "tekst trafia do modelu AI"],
  ] as const)(
    "%s notice under an AI field links to the policy in its language",
    async (locale, href, text) => {
      const html = await render(locale, createElement(AiInputNotice, { className: "field__hint" }));
      expect(html).toContain(text);
      expect(html).toContain(`href="${href}"`);
      expect(html).toContain('target="_blank"');
    },
  );

  it.each([
    ["../components/MissingDiseaseDialog.tsx", 'className="miss-modal__hint"'],
    ["./StartResearchView.tsx", 'className="field__hint"'],
  ])("%s carries the notice under its field", (file, hintClass) => {
    // The wider search sends its text to a model, and so does starting research on a new disease.
    const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8");
    expect(source).toContain(`<AiInputNotice ${hintClass} />`);
  });
});
