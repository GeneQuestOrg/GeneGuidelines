import { useTranslation } from "react-i18next";
import { useDisease } from "../hooks/useDisease";
import { useSourceShelf } from "../hooks/useSourceShelf";
import { useOfficialGuideline } from "../hooks/useOfficialGuideline";
import { PlaceholderView } from "./PlaceholderView";
import "../styles/disease-map.css";

export interface DiseaseMapViewProps {
  readonly slug: string;
  readonly onNav: (path: string) => void;
}

/**
 * Parent "orientation map" (draft12 "Widok choroby - mapa rodzica"): the
 * unknown-unknowns narrative spine a freshly-diagnosed family walks, NOT a data
 * hub. The prose is hand-authored and editorial (the orientation voice is the
 * product); only the disease facts, the action-button counts, and the
 * guideline-exists state are wired to live data. Founder anchors are the FD
 * diagnostic-odyssey and show only for FD; the spine itself is disease-agnostic.
 *
 * Lives at /diseases/{slug}/map alongside the existing data-hub /diseases/{slug}
 * so the two can be compared before deciding which becomes the parent default.
 */
export function DiseaseMapView({ slug, onNav }: DiseaseMapViewProps) {
  const { t } = useTranslation("disease-map");
  const { disease, loading, error } = useDisease(slug);
  const { docs: sourceDocs } = useSourceShelf(slug);
  const { pointer: officialPointer } = useOfficialGuideline(slug);

  if (loading) {
    return (
      <section className="page">
        <div className="dmap">
          <p className="dmap-loading">{t("loading")}</p>
        </div>
      </section>
    );
  }

  if (error != null || disease == null) {
    return (
      <PlaceholderView
        title={t("notFoundTitle")}
        description={error ?? t("notFoundDesc", { slug })}
        primaryAction={{ label: t("notFoundAction"), path: "/diseases" }}
        onNav={onNav}
      />
    );
  }

  const isFd = slug === "fd";
  const hasGuideline = sourceDocs.length > 0 || officialPointer != null;
  const nameShort = disease.nameShort || disease.name;
  const go = (path: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    onNav(path);
  };

  return (
    <section className="page">
      <div className="dmap">
        <nav className="dmap-crumb" aria-label={t("crumbAriaLabel")}>
          <a href="/diseases" onClick={go("/diseases")}>
            {t("crumbDiseases")}
          </a>
          <span className="dmap-crumb__sep">/</span>
          <span>{disease.name}</span>
        </nav>

        {/* HERO */}
        <section className="dmap-hero">
          <div className="dmap-eyebrow">
            <span className="dmap-eyebrow__dot" aria-hidden />
            {t("eyebrow")} <span className="dmap-eyebrow__sep">·</span> {disease.name}
          </div>
          <h1 className="dmap-title">
            {t("heroTitlePrefix")} <em>{t("heroTitleEm")}</em>.
          </h1>
          <p className="dmap-lede">
            {t("heroLedePart1")}{" "}
            <b>{t("heroLedeBold1")}</b> {t("heroLedePart2")} <em>{t("heroLedeEm")}</em>{" "}
            {t("heroLedePart3")}{" "}
            <b>{t("heroLedeBold2")}</b>
          </p>

          <div className="dmap-facts">
            {disease.gene ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">{t("factGene")}</span> <code>{disease.gene}</code>
              </span>
            ) : null}
            {disease.inheritance ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">{t("factInheritance")}</span> {disease.inheritance}
              </span>
            ) : null}
            {disease.prevalenceText ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">{t("factPrevalence")}</span> {disease.prevalenceText}
              </span>
            ) : null}
            {disease.omim ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">{t("factOmim")}</span> <code>{disease.omim}</code>
              </span>
            ) : null}
          </div>

          <div className="dmap-privacy">
            <span className="dmap-privacy__ic" aria-hidden>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </span>
            <div className="dmap-privacy__b">
              <b>{t("privacyTitle")}</b> {t("privacyBodyPart1")} <em>{t("privacyBodyEm")}</em>{" "}
              {t("privacyBodyPart2")}{" "}
              <button type="button" onClick={go(`/diseases/${slug}/my-case`)}>
                {t("privacyCta")}
              </button>
            </div>
          </div>
        </section>

        {/* MAP INTRO */}
        <section className="dmap-intro">
          <div className="dmap-intro__kicker">
            <span className="dmap-intro__dot" aria-hidden />
            {t("introKicker")}
          </div>
          <h2 className="dmap-intro__title">{t("introTitle")}</h2>
          <p className="dmap-intro__sub">{t("introSub")}</p>
        </section>

        <div className="dmap-steps">
          {/* STEP 1 — verify the diagnosis */}
          <article className="dmap-step">
            <div className="dmap-step__rail">
              <div className="dmap-step__num">1</div>
            </div>
            <div className="dmap-step__body">
              <span className="dmap-step__hook">
                <span className="dmap-step__tri" aria-hidden>◆</span>
                {t("step1Hook")}
              </span>
              <h3 className="dmap-step__title">{t("step1Title")}</h3>
              <p className="dmap-step__lede">
                {isFd ? (
                  <>
                    {t("step1LedeFdPart1")} <b>{t("step1LedeFdBold1")}</b>{" "}
                    {t("step1LedeFdPart2")} <em>{t("step1LedeFdEm")}</em>{" "}
                    {t("step1LedeFdPart3")} <b>{t("step1LedeFdBold2")}</b>
                    {t("step1LedeFdPart4")}
                  </>
                ) : (
                  <>
                    {t("step1LedeGenericPart1")} <b>{t("step1LedeGenericBold")}</b>{" "}
                    {t("step1LedeGenericPart2")}
                  </>
                )}
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">{t("anchorLabel")}</div>
                  <div className="dmap-anchor__q">{t("step1AnchorQuote")}</div>
                </div>
              ) : null}
              <div className="dmap-actions">
                {hasGuideline ? (
                  <a
                    className="dmap-btn dmap-btn--accent"
                    href={`/diseases/${slug}/guidelines`}
                    onClick={go(`/diseases/${slug}/guidelines`)}
                  >
                    {t("step1CtaConfirm")}
                    <span className="dmap-btn__arr" aria-hidden>→</span>
                  </a>
                ) : null}
                <a
                  className="dmap-btn"
                  href={`/diseases/${slug}/my-case`}
                  onClick={go(`/diseases/${slug}/my-case`)}
                >
                  {t("step1CtaQuestions")}
                </a>
              </div>
            </div>
          </article>

          {/* STEP 2 — find doctors who know it */}
          <article className="dmap-step">
            <div className="dmap-step__rail">
              <div className="dmap-step__num">2</div>
            </div>
            <div className="dmap-step__body">
              <span className="dmap-step__hook">
                <span className="dmap-step__tri" aria-hidden>◆</span>
                {t("step2Hook")}
              </span>
              <h3 className="dmap-step__title">{t("step2Title", { name: nameShort })}</h3>
              <p className="dmap-step__lede">
                {t("step2LedePart1")} <em>{t("step2LedeEm")}</em> {t("step2LedePart2")}{" "}
                <b>{t("step2LedeBold")}</b> {t("step2LedePart3")}
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">{t("anchorLabel")}</div>
                  <div className="dmap-anchor__q">{t("step2AnchorQuote")}</div>
                </div>
              ) : null}
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`/doctors?disease=${slug}`}
                  onClick={go(`/doctors?disease=${slug}`)}
                >
                  {t("step2CtaFind", { name: nameShort })}
                  {disease.doctorsCount > 0 ? (
                    <span className="dmap-nub">{disease.doctorsCount}</span>
                  ) : null}
                  <span className="dmap-btn__arr" aria-hidden>→</span>
                </a>
                <a className="dmap-btn" href="/doctors" onClick={go("/doctors")}>
                  {t("step2CtaRecommend")}
                </a>
              </div>
            </div>
          </article>

          {/* STEP 3 — guidelines */}
          <article className="dmap-step">
            <div className="dmap-step__rail">
              <div className="dmap-step__num">3</div>
            </div>
            <div className="dmap-step__body">
              <span className="dmap-step__hook">
                <span className="dmap-step__tri" aria-hidden>◆</span>
                {hasGuideline ? t("step3HookExists") : t("step3HookAssembling")}
              </span>
              <h3 className="dmap-step__title">
                {hasGuideline
                  ? t("step3TitleExists", { name: nameShort })
                  : t("step3TitleAssembling", { name: nameShort })}
              </h3>
              <p className="dmap-step__lede">
                {t("step3LedePart1")} <b>{t("step3LedeBold")}</b> {t("step3LedePart2")}
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">{t("anchorLabel")}</div>
                  <div className="dmap-anchor__q">
                    {t("step3AnchorQuotePart1")} <em>{t("step3AnchorQuoteEm")}</em>{" "}
                    {t("step3AnchorQuotePart2")}
                  </div>
                </div>
              ) : null}
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`/diseases/${slug}/guidelines`}
                  onClick={go(`/diseases/${slug}/guidelines`)}
                >
                  {hasGuideline ? t("step3CtaOpen") : t("step3CtaSeeFar")}
                  <span className="dmap-btn__arr" aria-hidden>→</span>
                </a>
              </div>
            </div>
          </article>

          {/* STEP 4 — foundations */}
          <article className="dmap-step">
            <div className="dmap-step__rail">
              <div className="dmap-step__num">4</div>
            </div>
            <div className="dmap-step__body">
              <span className="dmap-step__hook">
                <span className="dmap-step__tri" aria-hidden>◆</span>
                {t("step4Hook")}
              </span>
              <h3 className="dmap-step__title">{t("step4Title")}</h3>
              <p className="dmap-step__lede">
                {t("step4LedePart1")} <b>{t("step4LedeBold")}</b>
                {t("step4LedePart2")}
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">{t("anchorLabel")}</div>
                  <div className="dmap-anchor__q">{t("step4AnchorQuote")}</div>
                </div>
              ) : null}
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`/diseases/${slug}`}
                  onClick={go(`/diseases/${slug}`)}
                >
                  {t("step4Cta", { name: nameShort })}
                  <span className="dmap-btn__arr" aria-hidden>→</span>
                </a>
              </div>
            </div>
          </article>

          {/* STEP 5 — trials */}
          <article className="dmap-step">
            <div className="dmap-step__rail">
              <div className="dmap-step__num">5</div>
            </div>
            <div className="dmap-step__body">
              <span className="dmap-step__hook">
                <span className="dmap-step__tri" aria-hidden>◆</span>
                {t("step5Hook")}
              </span>
              <h3 className="dmap-step__title">{t("step5Title")}</h3>
              <p className="dmap-step__lede">
                {t("step5LedePart1")} <b>{t("step5LedeBold")}</b> {t("step5LedePart2")}
              </p>
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`/diseases/${slug}`}
                  onClick={go(`/diseases/${slug}`)}
                >
                  {t("step5CtaTrials")}
                  {disease.trialsCount > 0 ? (
                    <span className="dmap-nub">{disease.trialsCount}</span>
                  ) : null}
                  <span className="dmap-btn__arr" aria-hidden>→</span>
                </a>
                <a className="dmap-btn" href={`/diseases/${slug}`} onClick={go(`/diseases/${slug}`)}>
                  {t("step5CtaTherapies")}
                </a>
              </div>
            </div>
          </article>

          {/* STEP 0 — pre-diagnosis */}
          <article className="dmap-step">
            <div className="dmap-step__rail">
              <div className="dmap-step__num dmap-step__num--zero">0</div>
            </div>
            <div className="dmap-step__body">
              <span className="dmap-step__hook">
                <span className="dmap-step__tri" aria-hidden>◆</span>
                {t("step0Hook")}
              </span>
              <h3 className="dmap-step__title">{t("step0Title")}</h3>
              <div className="dmap-predx">
                <span className="dmap-predx__tag">{t("step0Tag")}</span>
                <h4 className="dmap-predx__title">{t("step0PredxTitle")}</h4>
                <p className="dmap-predx__lede">
                  {t("step0PredxLedePart1")} <b>{t("step0PredxLedeBold1")}</b>
                  {t("step0PredxLedePart2")} <b>{t("step0PredxLedeBold2")}</b>{" "}
                  {t("step0PredxLedePart3")}
                </p>
              </div>
            </div>
          </article>
        </div>

        {/* SAFETY */}
        <div className="dmap-safety">
          <span className="dmap-safety__ic" aria-hidden>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8h.01M11 12h1v4h1" />
            </svg>
          </span>
          <div className="dmap-safety__b">
            <b>{t("safetyBold")}</b> {t("safetyBody")}
          </div>
        </div>

        <footer className="dmap-foot">
          <b>GeneGuidelines</b> {t("footerPart1")}{" "}
          <em>{t("footerEm")}</em>
        </footer>
      </div>
    </section>
  );
}
