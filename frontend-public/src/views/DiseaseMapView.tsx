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
  const { disease, loading, error } = useDisease(slug);
  const { docs: sourceDocs } = useSourceShelf(slug);
  const { pointer: officialPointer } = useOfficialGuideline(slug);

  if (loading) {
    return (
      <section className="page">
        <div className="dmap">
          <p className="dmap-loading">Loading orientation map…</p>
        </div>
      </section>
    );
  }

  if (error != null || disease == null) {
    return (
      <PlaceholderView
        title="Disease not found"
        description={
          error ?? `No catalog entry for “${slug}”. Try browsing the disease list.`
        }
        primaryAction={{ label: "Browse diseases", path: "/diseases" }}
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
        <nav className="dmap-crumb" aria-label="breadcrumb">
          <a href="#/diseases" onClick={go("/diseases")}>
            Diseases
          </a>
          <span className="dmap-crumb__sep">/</span>
          <span>{disease.name}</span>
        </nav>

        {/* HERO */}
        <section className="dmap-hero">
          <div className="dmap-eyebrow">
            <span className="dmap-eyebrow__dot" aria-hidden />
            Freshly diagnosed <span className="dmap-eyebrow__sep">·</span> {disease.name}
          </div>
          <h1 className="dmap-title">
            What we wish we&rsquo;d known <em>in the first week</em>.
          </h1>
          <p className="dmap-lede">
            Right after a diagnosis the hardest part isn&rsquo;t the missing answers — it&rsquo;s{" "}
            <b>not knowing what to even ask.</b> That you have to see the diagnosis through
            yourself. That a doctor who knows <em>this</em> disease exists. That guidelines,
            foundations, and trials exist. Below you&rsquo;re not searching —{" "}
            <b>you&rsquo;re reading a map of the things nobody told you about.</b>
          </p>

          <div className="dmap-facts">
            {disease.gene ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">Gene</span> <code>{disease.gene}</code>
              </span>
            ) : null}
            {disease.inheritance ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">Inheritance</span> {disease.inheritance}
              </span>
            ) : null}
            {disease.prevalenceText ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">Prevalence</span> {disease.prevalenceText}
              </span>
            ) : null}
            {disease.omim ? (
              <span className="dmap-fact">
                <span className="dmap-fact__k">OMIM</span> <code>{disease.omim}</code>
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
              <b>Have a hospital discharge summary?</b> You can load it privately — facts are
              extracted locally in your browser, the original never reaches us. Then the map
              below adapts to <em>your</em> case and mutation.{" "}
              <button type="button" onClick={go(`/diseases/${slug}/my-case`)}>
                Load privately →
              </button>
            </div>
          </div>
        </section>

        {/* MAP INTRO */}
        <section className="dmap-intro">
          <div className="dmap-intro__kicker">
            <span className="dmap-intro__dot" aria-hidden />
            Orientation map
          </div>
          <h2 className="dmap-intro__title">
            Six things you don&rsquo;t know to ask about — in the order you&rsquo;ll need them.
          </h2>
          <p className="dmap-intro__sub">
            This isn&rsquo;t a feature list. It&rsquo;s the path a family walks after a
            diagnosis — each stop tells you what exists and what to do with it.
          </p>
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
                Nobody tells you the diagnosis is yours to double-check
              </span>
              <h3 className="dmap-step__title">
                First, make sure it&rsquo;s really this disease — and this subtype.
              </h3>
              <p className="dmap-step__lede">
                {isFd ? (
                  <>
                    FD is confirmed <b>genetically</b> (a GNAS mutation) and on imaging —{" "}
                    <em>not</em> by biopsy alone. The guideline says outright when a biopsy{" "}
                    <b>is not needed</b>, yet it is sometimes done routinely. Before anyone
                    proposes treatment, the diagnosis and subtype (mono- vs polyostotic) must
                    be certain.
                  </>
                ) : (
                  <>
                    Many rare diseases look like more common ones on a first pass. Before anyone
                    proposes treatment, the diagnosis and subtype must be confirmed — often{" "}
                    <b>molecularly</b> and on imaging, not by one test in isolation.
                  </>
                )}
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">From our journey</div>
                  <div className="dmap-anchor__q">
                    &ldquo;In Warsaw our son had a histopathology the guideline didn&rsquo;t
                    require — and got a wrong diagnosis. Only the CT in Olsztyn and the GNAS test
                    settled it.&rdquo;
                  </div>
                </div>
              ) : null}
              <div className="dmap-actions">
                {hasGuideline ? (
                  <a
                    className="dmap-btn dmap-btn--accent"
                    href={`#/diseases/${slug}/guidelines`}
                    onClick={go(`/diseases/${slug}/guidelines`)}
                  >
                    What to confirm, and in what order
                    <span className="dmap-btn__arr" aria-hidden>→</span>
                  </a>
                ) : null}
                <a
                  className="dmap-btn"
                  href={`#/diseases/${slug}/my-case`}
                  onClick={go(`/diseases/${slug}/my-case`)}
                >
                  Questions for your doctor
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
                Not every surgeon or endocrinologist knows this disease
              </span>
              <h3 className="dmap-step__title">
                A handful of doctors truly know {nameShort}. Find them.
              </h3>
              <p className="dmap-step__lede">
                In a rare disease the most valuable — and hardest to find — person is a doctor
                who <em>really</em> knows this condition. We show the{" "}
                <b>level of documented experience</b> (from PubMed: whether they have published
                on it, co-authored studies, or led them) and family recommendations — sorted by
                distance from you.
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">From our journey</div>
                  <div className="dmap-anchor__q">
                    &ldquo;We found the best doctors by word of mouth and by chance at a check-up —
                    not from a search engine. That&rsquo;s why a parent can add a doctor here, with
                    a note.&rdquo;
                  </div>
                </div>
              ) : null}
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`#/doctors?disease=${slug}`}
                  onClick={go(`/doctors?disease=${slug}`)}
                >
                  Doctors who know {nameShort} near you
                  {disease.doctorsCount > 0 ? (
                    <span className="dmap-nub">{disease.doctorsCount}</span>
                  ) : null}
                  <span className="dmap-btn__arr" aria-hidden>→</span>
                </a>
                <a className="dmap-btn" href="#/doctors" onClick={go("/doctors")}>
                  Recommend a doctor
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
                {hasGuideline
                  ? "Yes — guidance for this disease already exists"
                  : "Guidance is being assembled for this disease"}
              </span>
              <h3 className="dmap-step__title">
                {hasGuideline
                  ? `Someone already wrote down how to manage ${nameShort}. Read it before your visit.`
                  : `Read what's known about managing ${nameShort} before your visit.`}
              </h3>
              <p className="dmap-step__lede">
                From the guidelines we pull out <b>concrete, actionable steps</b> — diagnosis,
                monitoring, red flags, when to seek a second opinion — instead of a wall of text
                written for a specialist. Every sentence links to its source, and newer
                &ldquo;to consider&rdquo; recommendations are clearly labelled.
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">From our journey</div>
                  <div className="dmap-anchor__q">
                    &ldquo;The FD guideline said plainly what is <em>not</em> done in a child — and
                    Munich recommended exactly that. The knowledge existed; it just hadn&rsquo;t
                    reached us.&rdquo;
                  </div>
                </div>
              ) : null}
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`#/diseases/${slug}/guidelines`}
                  onClick={go(`/diseases/${slug}/guidelines`)}
                >
                  {hasGuideline ? "Open the guideline — synthesis + sources" : "See what we have so far"}
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
                Travel to specialists and tests cost money — help exists
              </span>
              <h3 className="dmap-step__title">You don&rsquo;t have to fund this journey alone.</h3>
              <p className="dmap-step__lede">
                International and local foundations offer <b>community, grants, and advocacy</b>.
                We also show how to start and spread a fundraiser for travel to specialists,
                visits, and tests — something a freshly-diagnosed family rarely thinks of at the
                start.
              </p>
              {isFd ? (
                <div className="dmap-anchor">
                  <div className="dmap-anchor__lbl">From our journey</div>
                  <div className="dmap-anchor__q">
                    &ldquo;The international FDMAS Alliance had been there all along — but we had to
                    find it ourselves, over months.&rdquo;
                  </div>
                </div>
              ) : null}
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`#/diseases/${slug}`}
                  onClick={go(`/diseases/${slug}`)}
                >
                  Foundations supporting {nameShort}
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
                Taking part in a trial can be the best available therapy
              </span>
              <h3 className="dmap-step__title">
                Check whether someone is testing something for your child.
              </h3>
              <p className="dmap-step__lede">
                Actively recruiting trials, linked to ClinicalTrials.gov, sorted by distance.
                When you load your case privately,{" "}
                <b>we&rsquo;ll alert you when a trial matching your mutation appears</b> — so you
                don&rsquo;t have to check by hand every week.
              </p>
              <div className="dmap-actions">
                <a
                  className="dmap-btn dmap-btn--accent"
                  href={`#/diseases/${slug}`}
                  onClick={go(`/diseases/${slug}`)}
                >
                  Clinical trials near you
                  {disease.trialsCount > 0 ? (
                    <span className="dmap-nub">{disease.trialsCount}</span>
                  ) : null}
                  <span className="dmap-btn__arr" aria-hidden>→</span>
                </a>
                <a className="dmap-btn" href={`#/diseases/${slug}`} onClick={go(`/diseases/${slug}`)}>
                  Promising therapies and their status
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
                And if no one knows yet what&rsquo;s wrong?
              </span>
              <h3 className="dmap-step__title">Before there&rsquo;s even a diagnosis.</h3>
              <div className="dmap-predx">
                <span className="dmap-predx__tag">planned module · preliminary orientation</span>
                <h4 className="dmap-predx__title">A deep, adaptive intake interview</h4>
                <p className="dmap-predx__lede">
                  Sometimes the problem isn&rsquo;t &ldquo;I have a diagnosis, what now&rdquo; but{" "}
                  <b>&ldquo;the doctors don&rsquo;t know what&rsquo;s wrong&rdquo;</b>. The
                  interview works iteratively: it takes a broad first pass, then — depending on
                  your answers — can search the literature before asking the next question. The
                  goal is not diagnostic: it&rsquo;s <b>preliminary orientation</b> — which leads
                  to explore, which specialist to consider, what to ask — written up as a document
                  to discuss with your doctor.
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
            <b>Everything here is a starting point for a conversation with your doctor — not a
            recommendation.</b>{" "}
            We show official guidelines plainly; &ldquo;to consider&rdquo; recommendations and AI
            drafts always carry a label, a rationale, and a &ldquo;discuss with your doctor&rdquo;
            note. Your doctor makes the decisions — we help you know what to ask.
          </div>
        </div>

        <footer className="dmap-foot">
          <b>GeneGuidelines</b> — open infrastructure for rare-disease guidelines, maintained by
          the GeneQuest Foundation. We test every design decision with one question:{" "}
          <em>would this have helped our son?</em>
        </footer>
      </div>
    </section>
  );
}
