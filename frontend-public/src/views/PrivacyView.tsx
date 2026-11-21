import { useEffect, type MouseEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import enPrivacy from "../locales/en/privacy.json";
import plPrivacy from "../locales/pl/privacy.json";
import {
  PRIVACY_POLICY_VERSION,
  VERSION_PLACEHOLDER,
  formatPolicyVersion,
  inlineTokens,
  privacyPolicyHref,
} from "../content/privacyPolicy.mjs";
import type { Locale } from "../router/locale";
import "./about-view.css";
import "./privacy-view.css";

export interface PrivacyViewProps {
  /** Switch language on this same page — the link to the other version is a language switch, not an in-app navigation (which keeps the current language). */
  onSetLocale: (locale: Locale) => void;
}

type PolicyBlock = { p: string } | { ol: string[] } | { ul: string[] };

interface PolicySection {
  id: string;
  heading: string;
  blocks: PolicyBlock[];
}

interface PrivacyContent {
  ui: { tocHeading: string; otherLanguage: string };
  policy: { title: string; version: string; sections: PolicySection[] };
}

/**
 * Read straight from the catalogues, not through i18next: this is legal text, so a Polish key that went missing must not quietly fall back to the English translation, and nothing in it may be interpolated except the version date. The prerender reads the same files (prerender/pages.mjs).
 */
const CONTENT: Record<Locale, PrivacyContent> = {
  en: enPrivacy as PrivacyContent,
  pl: plPrivacy as PrivacyContent,
};

function asLocale(language: string | undefined): Locale {
  return language === "pl" ? "pl" : "en";
}

/** One string of the policy, with its bold leads, storage key names and email addresses marked up. */
function Inline({ text }: { text: string }): ReactNode {
  return inlineTokens(text).map((token, i) => {
    switch (token.kind) {
      case "bold":
        return <b key={i}>{token.value}</b>;
      case "code":
        return <code key={i}>{token.value}</code>;
      case "email":
        return (
          <a key={i} className="about__link" href={`mailto:${token.value}`}>
            {token.value}
          </a>
        );
      default:
        return token.value;
    }
  });
}

function Block({ block }: { block: PolicyBlock }): ReactNode {
  if ("p" in block) {
    return (
      <p>
        <Inline text={block.p} />
      </p>
    );
  }
  const items = "ol" in block ? block.ol : block.ul;
  const list = items.map((item, i) => (
    <li key={i}>
      <Inline text={item} />
    </li>
  ));
  return "ol" in block ? (
    <ol className="about__bullets privacy__list">{list}</ol>
  ) : (
    <ul className="about__bullets privacy__list">{list}</ul>
  );
}

/** "Wersja: 21 listopada 2026. Polityka jest zgodna…" — the date comes from one constant, never the draft's placeholder. */
function VersionLine({ template, locale }: { template: string; locale: Locale }): ReactNode {
  const [before, after = ""] = template.split(VERSION_PLACEHOLDER);
  return (
    <p className="privacy__version">
      <Inline text={before} />
      <time dateTime={PRIVACY_POLICY_VERSION}>{formatPolicyVersion(locale)}</time>
      <Inline text={after} />
    </p>
  );
}

function scrollToSection(sectionId: string): void {
  document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function PrivacyToc({ heading, sections }: { heading: string; sections: PolicySection[] }) {
  const links = (
    <ul className="about__toc-list">
      {sections.map((section) => (
        <li key={section.id}>
          <a
            href={`#${section.id}`}
            onClick={(e) => {
              e.preventDefault();
              scrollToSection(section.id);
            }}
          >
            {section.heading}
          </a>
        </li>
      ))}
    </ul>
  );
  return (
    <nav className="about__toc" aria-label={heading}>
      <details className="about__toc-collapse">
        <summary className="about__toc-summary">{heading}</summary>
        {links}
      </details>
      <div className="about__toc-desktop">
        <div className="about__toc-label">{heading}</div>
        {links}
      </div>
    </nav>
  );
}

/**
 * The privacy policy: Polish at /pl/privacy (binding), the English translation at /privacy. Same layout and type as the About page — a long text to read, with the section list beside it (above it on a phone).
 */
export function PrivacyView({ onSetLocale }: PrivacyViewProps) {
  const { i18n } = useTranslation();
  const locale = asLocale(i18n.resolvedLanguage ?? i18n.language);
  const { ui, policy } = CONTENT[locale];
  const other: Locale = locale === "pl" ? "en" : "pl";

  // A link to one section (the clinician form points at #clinicians) opens a fresh page; the static copy that held the anchor is gone by the time the app has mounted, so scroll to it again.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) {
      document.getElementById(id)?.scrollIntoView({ block: "start" });
    }
  }, []);

  const switchLanguage = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return;
    }
    e.preventDefault();
    onSetLocale(other);
  };

  return (
    <div className="page page--about page--privacy">
      <header id="top" className="about__hero privacy__hero">
        <h1 className="about__lead privacy__title">{policy.title}</h1>
        <VersionLine template={policy.version} locale={locale} />
        <p className="privacy__language">
          <a
            className="about__link"
            href={privacyPolicyHref(other)}
            hrefLang={other}
            lang={other}
            onClick={switchLanguage}
          >
            {ui.otherLanguage}
          </a>
        </p>
      </header>

      <div className="about__layout">
        <PrivacyToc heading={ui.tocHeading} sections={policy.sections} />
        <article className="about__article privacy__article">
          {policy.sections.map((section) => (
            <section key={section.id} id={section.id} className="about__sec">
              <h2 className="about__h2">{section.heading}</h2>
              {section.blocks.map((block, i) => (
                <Block key={i} block={block} />
              ))}
            </section>
          ))}
        </article>
      </div>
    </div>
  );
}
