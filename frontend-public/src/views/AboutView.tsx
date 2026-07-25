import { Button } from "@gene-guidelines/ui";
import { useTranslation } from "react-i18next";
import type { AudienceView } from "../router/types";
import "./about-view.css";

export interface AboutViewProps {
  view: AudienceView;
  onNav: (path: string) => void;
}

interface AboutTocItem {
  id: string;
  indent?: boolean;
}

const ABOUT_TOC: AboutTocItem[] = [
  { id: "top" },
  { id: "origins" },
  { id: "scale" },
  { id: "specialist" },
  { id: "families", indent: true },
  { id: "clinicians", indent: true },
  { id: "disease-page" },
  { id: "how" },
  { id: "privacy" },
  { id: "not" },
  { id: "limitations" },
  { id: "about" },
];

function scrollToAboutSection(sectionId: string): void {
  document.getElementById(sectionId)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function AboutTocLinks() {
  const { t } = useTranslation("about");
  return (
    <ul className="about__toc-list">
      {ABOUT_TOC.map((item) => (
        <li key={item.id} className={item.indent ? "about__toc-item--indent" : undefined}>
          <a
            href={`#${item.id}`}
            onClick={(e) => {
              e.preventDefault();
              scrollToAboutSection(item.id);
            }}
          >
            {t(`toc.${item.id}`)}
          </a>
        </li>
      ))}
    </ul>
  );
}

function AboutTableOfContents() {
  const { t } = useTranslation("about");
  return (
    <nav className="about__toc" aria-label={t("toc.heading")}>
      <details className="about__toc-collapse">
        <summary className="about__toc-summary">{t("toc.heading")}</summary>
        <AboutTocLinks />
      </details>
      <div className="about__toc-desktop">
        <div className="about__toc-label">{t("toc.heading")}</div>
        <AboutTocLinks />
      </div>
    </nav>
  );
}

export function AboutView({ onNav }: AboutViewProps) {
  const { t } = useTranslation("about");
  const originsParagraphs = t("origins.paragraphs", {
    returnObjects: true,
  }) as unknown as string[];
  const limitationItems = t("limitations.items", {
    returnObjects: true,
  }) as unknown as { lead: string; body: string }[];

  return (
    <div className="page page--about">
      <header id="top" className="about__hero">
        <div className="about__eyebrow">{t("hero.eyebrow")}</div>
        <div className="about__eyebrow-sub">{t("hero.eyebrowSub")}</div>
        <h1 className="about__lead">
          {t("hero.leadText1")}
          <b>{t("hero.leadNum")}</b>
          {t("hero.leadText2")}
          <br />
          {t("hero.leadLine2")}
          <br />
          {t("hero.leadLine3")}
        </h1>
        <p className="about__hero-tldr">{t("hero.tldr")}</p>
      </header>

      <div className="about__layout">
        <AboutTableOfContents />

        <article className="about__article">
          <section id="origins" className="about__sec">
            <h2 className="about__h2">{t("origins.heading")}</h2>
            {originsParagraphs.map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </section>

          <section id="scale" className="about__sec">
            <h2 className="about__h2">{t("scale.heading")}</h2>

            <div className="about__stats">
              <div className="about__stat">
                <div className="about__stat-num">{t("scale.stats.people.num")}</div>
                <div className="about__stat-label">
                  {t("scale.stats.people.text1")}
                  <b>{t("scale.stats.people.pct1")}</b>
                  {t("scale.stats.people.text2")}
                  <b>{t("scale.stats.people.pct2")}</b>
                  {t("scale.stats.people.text3")}
                  <span className="about__cite">
                    (
                    <a
                      href="https://www.nature.com/articles/s41431-019-0508-0"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("scale.stats.people.cite1")}
                    </a>
                    ;{" "}
                    <a
                      href="https://www.thelancet.com/journals/langlo/article/PIIS2214-109X(24)00056-1/fulltext"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("scale.stats.people.cite2")}
                    </a>
                    )
                  </span>
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">{t("scale.stats.described.num")}</div>
                <div className="about__stat-label">{t("scale.stats.described.label")}</div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">{t("scale.stats.pubs.num")}</div>
                <div className="about__stat-label">
                  {t("scale.stats.pubs.text1")}
                  <span className="about__cite">
                    (
                    <a
                      href="https://www.nlm.nih.gov/bsd/medline_pubmed_production_stats.html"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("scale.stats.pubs.cite")}
                    </a>
                    ).
                  </span>{" "}
                  {t("scale.stats.pubs.text2")}
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">{t("scale.stats.lag.num")}</div>
                <div className="about__stat-label">
                  {t("scale.stats.lag.text1")}
                  <span className="about__cite">
                    ({t("scale.stats.lag.citePrefix")}
                    <a
                      href="https://pubmed.ncbi.nlm.nih.gov/39592333/"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("scale.stats.lag.citeLink")}
                    </a>
                    )
                  </span>
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">{t("scale.stats.diagnosis.num")}</div>
                <div className="about__stat-label">
                  {t("scale.stats.diagnosis.text1")}
                  <span className="about__cite">
                    (
                    <a
                      href="https://www.thelancet.com/journals/langlo/article/PIIS2214-109X(24)00056-1/fulltext"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("scale.stats.diagnosis.citeLink")}
                    </a>
                    )
                  </span>
                </div>
              </div>
            </div>

            <p>{t("scale.closing")}</p>
          </section>

          <section id="specialist" className="about__sec">
            <h2 className="about__h2">{t("specialist.heading")}</h2>

            <h3 id="families" className="about__h3">
              {t("specialist.families.heading")}
            </h3>
            <p>
              {t("specialist.families.p1Lead")}
              <em>{t("specialist.families.p1Em")}</em>
              {t("specialist.families.p1Rest")}
            </p>
            <p>{t("specialist.families.p2")}</p>
            <p>
              {t("specialist.families.p3Text1")}
              <b>{t("specialist.families.p3Bold")}</b>
              {t("specialist.families.p3Text2")}
            </p>
            <p>{t("specialist.families.p4")}</p>
            <ol className="about__steps">
              <li>
                <b>{t("specialist.families.step1Lead")}</b>
                {t("specialist.families.step1Body")}
              </li>
              <li>
                <b>{t("specialist.families.step2Lead")}</b>
                {t("specialist.families.step2Body1")}
                <em>{t("specialist.families.step2Em")}</em>
                {t("specialist.families.step2Body2")}
              </li>
            </ol>

            <h3 id="clinicians" className="about__h3">
              {t("specialist.clinicians.heading")}
            </h3>
            <p>{t("specialist.clinicians.p1")}</p>
            <p>{t("specialist.clinicians.p2")}</p>
            <ul className="about__bullets">
              <li>
                <b>{t("specialist.clinicians.bullet1Lead")}</b>
                {t("specialist.clinicians.bullet1Body")}
              </li>
              <li>
                <b>{t("specialist.clinicians.bullet2Lead")}</b>
                {t("specialist.clinicians.bullet2Body1")}
                <em>{t("specialist.clinicians.bullet2Em")}</em>
                {t("specialist.clinicians.bullet2Body2")}
              </li>
            </ul>
          </section>

          <section id="disease-page" className="about__sec">
            <h2 className="about__h2">{t("diseasePage.heading")}</h2>
            <p>{t("diseasePage.intro")}</p>
            <ul className="about__bullets">
              <li>
                {t("diseasePage.item1Pre")}
                <b>{t("diseasePage.item1Bold")}</b>
                {t("diseasePage.item1Body")}
              </li>
              <li>
                {t("diseasePage.item2Pre")}
                <b>{t("diseasePage.item2Bold")}</b>
                {t("diseasePage.item2Body")}
              </li>
              <li>
                {t("diseasePage.item3Pre")}
                <b>{t("diseasePage.item3Bold")}</b>
                {t("diseasePage.item3Body")}
              </li>
              <li>
                <b>{t("diseasePage.item4Bold")}</b>
                {t("diseasePage.item4Body")}
              </li>
              <li>
                <b>{t("diseasePage.item5Bold")}</b>
                {t("diseasePage.item5Body")}
              </li>
              <li>
                <b>{t("diseasePage.item6Bold")}</b>
                {t("diseasePage.item6Body")}
              </li>
              <li>
                {t("diseasePage.item7Pre")}
                <b>{t("diseasePage.item7Bold")}</b>
                {t("diseasePage.item7Body1")}
                <em>{t("diseasePage.item7Em")}</em>
                {t("diseasePage.item7Body2")}
              </li>
            </ul>
            <p>{t("diseasePage.closing")}</p>
          </section>

          <section id="how" className="about__sec">
            <h2 className="about__h2">{t("how.heading")}</h2>
            <p>{t("how.p1")}</p>
            <p>
              {t("how.p2Text1")}
              <b>{t("how.p2Bold")}</b>
              {t("how.p2Text2")}
            </p>
            <p>
              {t("how.p3Text1")}
              <b>{t("how.p3Bold1")}</b>
              {t("how.p3Text2")}
              <b>{t("how.p3Bold2")}</b>
              {t("how.p3Text3")}
            </p>
            <ol className="about__pipeline">
              <li>
                <span className="about__pipeline-num">01</span>
                <div>
                  <b>{t("how.step1Title")}</b> {t("how.step1Body")}
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">02</span>
                <div>
                  <b>{t("how.step2Title")}</b> {t("how.step2Body")}
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">03</span>
                <div>
                  <b>{t("how.step3Title")}</b> {t("how.step3Body")}
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">04</span>
                <div>
                  <b>{t("how.step4Title")}</b> {t("how.step4Body1")}
                  <em>{t("how.step4Em")}</em>
                  {t("how.step4Body2")}
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">05</span>
                <div>
                  <b>{t("how.step5Title")}</b> {t("how.step5Body")}
                </div>
              </li>
            </ol>
          </section>

          <section id="privacy" className="about__sec">
            <h2 className="about__h2">{t("privacy.heading")}</h2>
            <p>
              {t("privacy.p1Text1")}
              <b>{t("privacy.p1Bold")}</b>
              {t("privacy.p1Text2")}
            </p>
            <p>{t("privacy.p2")}</p>
          </section>

          <section id="not" className="about__sec">
            <h2 className="about__h2">{t("not.heading")}</h2>
            <div className="about__nots">
              <div className="about__not">
                <h3>{t("not.diagnosticTitle")}</h3>
                <p>{t("not.diagnosticBody")}</p>
              </div>
              <div className="about__not">
                <h3>{t("not.chatbotTitle")}</h3>
                <p>{t("not.chatbotBody")}</p>
              </div>
              <div className="about__not">
                <h3>{t("not.consultationTitle")}</h3>
                <p>{t("not.consultationBody")}</p>
              </div>
              <div className="about__not">
                <h3>{t("not.commercialTitle")}</h3>
                <p>
                  {t("not.commercialBody1")}
                  <a
                    href="https://github.com/GeneQuestOrg/GeneGuidelines"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="about__link"
                  >
                    {t("not.commercialLink")}
                  </a>
                  {t("not.commercialBody2")}
                </p>
              </div>
            </div>
          </section>

          <section id="limitations" className="about__sec">
            <h2 className="about__h2">{t("limitations.heading")}</h2>
            <ul className="about__bullets about__bullets--candid">
              {limitationItems.map((item, i) => (
                <li key={i}>
                  <b>{item.lead}</b>
                  {item.body}
                </li>
              ))}
            </ul>
          </section>

          <section id="about" className="about__sec about__sec--who">
            <h2 className="about__h2">{t("who.heading")}</h2>
            <p>
              <b>{t("who.p1Bold")}</b>
              {t("who.p1Body")}
            </p>
            <p>{t("who.p2")}</p>
            <p className="about__contact">
              <Button variant="primary" onClick={() => window.open("mailto:kontakt@genequest.org")}>
                kontakt@genequest.org
              </Button>
            </p>
          </section>

          <section className="about__sec about__sec--cta">
            <h2 className="about__h2 about__h2--cta">{t("cta.heading")}</h2>
            <div className="about__ctas">
              <a
                href="/"
                className="about__cta"
                onClick={(e) => {
                  e.preventDefault();
                  onNav("/");
                }}
              >
                <span className="about__cta-label">{t("cta.diseaseLabel")}</span>
                <span className="about__cta-sub">{t("cta.diseaseSub")}</span>
                <span className="about__cta-arrow" aria-hidden>
                  →
                </span>
              </a>
              <a
                href="/doctors"
                className="about__cta"
                onClick={(e) => {
                  e.preventDefault();
                  onNav("/doctors");
                }}
              >
                <span className="about__cta-label">{t("cta.doctorsLabel")}</span>
                <span className="about__cta-sub">{t("cta.doctorsSub")}</span>
                <span className="about__cta-arrow" aria-hidden>
                  →
                </span>
              </a>
              <a
                href="/start-research"
                className="about__cta"
                onClick={(e) => {
                  e.preventDefault();
                  onNav("/start-research");
                }}
              >
                <span className="about__cta-label">{t("cta.researchLabel")}</span>
                <span className="about__cta-sub">{t("cta.researchSub")}</span>
                <span className="about__cta-arrow" aria-hidden>
                  →
                </span>
              </a>
            </div>
          </section>
        </article>
      </div>
    </div>
  );
}
