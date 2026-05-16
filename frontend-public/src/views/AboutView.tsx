import { Button } from "@gene-guidelines/ui";
import type { AudienceView } from "../router/types";
import { PersonaSwitcher } from "../components/PersonaSwitcher";
import "./about-view.css";

export interface AboutViewProps {
  view: AudienceView;
  onViewChange: (view: AudienceView) => void;
  onNav: (path: string) => void;
}

export function AboutView({ view, onViewChange, onNav }: AboutViewProps) {
  return (
    <div className="page page--about">
      <header className="about__hero">
        <div className="about__eyebrow">About the project</div>
        <h1 className="about__lead">
          PubMed indexes roughly <b>12,000</b> new articles on rare diseases every month.
          <br />
          Most of those diseases are tracked by a handful of researchers worldwide — rarely the doctor a family
          actually has access to.
          <br />
          GeneGuidelines exists to make that flow of knowledge usable at the point of care.
        </h1>
        <div className="about__persona">
          <PersonaSwitcher view={view} onChange={onViewChange} />
        </div>
      </header>

      <article className="about__article">
        <section className="about__sec">
          <h2 className="about__h2">Scale of the problem</h2>
          <p className="about__lede">
            A primary-care doctor or even a surgeon not knowing the latest management for your rare disease is
            not a sign of incompetence or bad will. It is a <b>structural consequence of the scale</b> of modern
            medical literature.
          </p>

          <div className="about__stats">
            <div className="about__stat">
              <div className="about__stat-num">~1.5 M</div>
              <div className="about__stat-label">
                New medical publications indexed by PubMed each year. Roughly 30 per day in rare diseases alone.
              </div>
            </div>
            <div className="about__stat">
              <div className="about__stat-num">~7,000</div>
              <div className="about__stat-label">
                Rare diseases described in OMIM and Orphanet. Most have fewer than 100 publications per year.
              </div>
            </div>
            <div className="about__stat">
              <div className="about__stat-num">~6 years</div>
              <div className="about__stat-label">
                Median lag from high-quality evidence appearing to its incorporation into formal clinical
                guidelines (Morris et al., 2011; Cochrane).
              </div>
            </div>
            <div className="about__stat">
              <div className="about__stat-num">~30 / month</div>
              <div className="about__stat-label">
                Distinct disease entities a typical primary-care doctor encounters in a single month of practice.
                Many of them rare.
              </div>
            </div>
          </div>

          <aside className="about__pull">
            <p>
              "How am I supposed to be up to date when even what I read two years ago is already obsolete?"
            </p>
            <cite>— primary-care physician, rare-disease conference workshop, Warsaw 2026</cite>
          </aside>
        </section>

        <section className="about__sec">
          <h2 className="about__h2">Why "a specialist" is not enough</h2>

          {view === "parent" ? (
            <>
              <p>
                Hearing "we'll refer you to a maxillofacial surgeon" is a good referral. But a maxillofacial
                surgeon with a world-class record in orthognathic surgery has not necessarily seen a child with
                fibrous dysplasia. The two competencies sit on different axes.
              </p>
              <p>
                In one documented case from a family working with GeneQuest, a treatment plan went through{" "}
                <em>three centres in three countries</em> before it reached a doctor familiar with paediatric FD.
                Only that last doctor halted the planned operation and pointed to the international standard:
                conservative management. Everyone before had been competent — none knew that specific disease.
              </p>
              <p>
                Looking for a doctor who has already treated dozens of patients with your specific disease is not
                paranoia or distrust of other doctors. It is a rational response to the fact that{" "}
                <b>clinical experience in a rare disease is concentrated in a narrow set of centres</b> — and
                finding them takes active effort.
              </p>
              <p>You can help your family doctor in two concrete ways:</p>
              <ol className="about__steps">
                <li>
                  <b>Bring them materials.</b> In each disease section on this site you'll find "Materials for
                  the family doctor" — a curated set of 3–5 peer-reviewed articles, ready to print or email.
                  Helps in 30 minutes.
                </li>
                <li>
                  <b>Or point them at the guideline document.</b> Each disease has a <em>living guideline</em>{" "}
                  maintained by specialists, updated monthly, with full citations. The same thing an expert in
                  Leiden or Rome would read.
                </li>
              </ol>
            </>
          ) : (
            <>
              <p>
                Clinical specialisation does not scale linearly with the number of diagnosed diseases. You know
                anatomy, surgical technique, pharmacology — but the specifics of a rare entity often need
                hundreds of published cases that would take weeks to read, regardless of seniority.
              </p>
              <p>
                This is not a competence problem — it is an attention-distribution problem. Each of us sees
                dozens of disease entities a month. A full read of the current literature for each one demands
                time that simply isn't there.
              </p>
              <p>GeneGuidelines is a tool for both sides of that asymmetry:</p>
              <ul className="about__bullets">
                <li>
                  <b>If you are seeing a patient with a disease rarely present in your practice</b> — open the
                  guideline document for that entity and get the current state of clinical knowledge, with
                  citations to the original publications and a provenance trail for every recommendation (who
                  approved it and when).
                </li>
                <li>
                  <b>If you are a specialist in a given disease</b> — you can join as a reviewer. Each month an
                  AI Watcher analyses new publications and proposes guideline updates. A review typically takes
                  15–30 minutes, and every decision is auditable (GitHub PR review model).
                </li>
              </ul>
            </>
          )}
        </section>

        <section className="about__sec">
          <h2 className="about__h2">How it works</h2>
          <p>
            GeneGuidelines does not replace reading the literature — it automates surfacing what is worth
            reading. Every change to a guideline document is approved by a competent human before publication.
          </p>
          <ol className="about__pipeline">
            <li>
              <span className="about__pipeline-num">01</span>
              <div>
                <b>AI Watcher monitors PubMed.</b> Every week it scans newly published articles for each disease
                in the catalog. Categorises publication type (case report / original research / review /
                consensus).
              </div>
            </li>
            <li>
              <span className="about__pipeline-num">02</span>
              <div>
                <b>Evaluator decides whether anything material has changed.</b> Is the new evidence strong enough
                to modify the current recommendation? Most articles do not require an update — and the system
                knows that.
              </div>
            </li>
            <li>
              <span className="about__pipeline-num">03</span>
              <div>
                <b>Draft pull request.</b> If the change is warranted, the AI proposes one — exactly the way an
                open-source contributor proposes a code change. Diff, citations, rationale.
              </div>
            </li>
            <li>
              <span className="about__pipeline-num">04</span>
              <div>
                <b>A specialist reviewer approves.</b> Approve / request changes / reject. Every decision signed
                by name, dated, and available in the audit trail.
              </div>
            </li>
            <li>
              <span className="about__pipeline-num">05</span>
              <div>
                <b>The document updates publicly.</b> Git-style versioning. You can open any past state of the
                document, and every paragraph carries its full provenance history.
              </div>
            </li>
          </ol>
        </section>

        <section className="about__sec">
          <h2 className="about__h2">What GeneGuidelines is NOT</h2>
          <div className="about__nots">
            <div className="about__not">
              <h3>Not a diagnostic tool</h3>
              <p>
                You do not enter symptoms or test results here. The system does not produce diagnoses. It
                operates at the level of guidelines for an already-diagnosed disease.
              </p>
            </div>
            <div className="about__not">
              <h3>Not a substitute for consultation</h3>
              <p>
                The materials here contribute to clinical discussion, not individual recommendations. Every
                therapeutic decision belongs to the attending physician.
              </p>
            </div>
            <div className="about__not">
              <h3>Does not collect patient data</h3>
              <p>
                You can use it anonymously. Notification sign-up is optional — without an email, preferences
                stay only in the user's browser.
              </p>
            </div>
            <div className="about__not">
              <h3>Not a commercial product</h3>
              <p>
                Built by the GeneQuest Foundation (KRS 0001211461). Open source. No ads, no paywall, no
                monetised API.
              </p>
            </div>
          </div>
        </section>

        <section className="about__sec">
          <h2 className="about__h2">What we don't know and don't do</h2>
          <ul className="about__bullets about__bullets--candid">
            <li>
              <b>Disease coverage is limited.</b> The MVP covers three entities (FD, MAS, Noonan). Adding a new
              one requires (a) a baseline guideline document as a starting point and (b) at least one specialist
              reviewer.
            </li>
            <li>
              <b>The doctor database is built from PubMed.</b> Publication activity is a decent proxy for
              scientific engagement but not a complete picture of clinical competence. A doctor excellent in
              practice who does not publish may be missed. Please report gaps.
            </li>
            <li>
              <b>AI can be over-optimistic.</b> Every automatically generated draft is filtered by a reviewer
              before publication. Subtle errors may still slip through. Any approved paragraph can be challenged
              at any time.
            </li>
            <li>
              <b>Translations.</b> Some literature is English-only; some documents currently exist in a single
              language version. We're working toward full multilingual coverage — slowly.
            </li>
          </ul>
        </section>

        <section className="about__sec about__sec--who">
          <h2 className="about__h2">Who is behind this</h2>
          <p>
            <b>GeneQuest Foundation</b> — a Polish non-profit focused on knowledge infrastructure for rare
            genetic diseases. KRS 0001211461. Starting point: fibrous dysplasia (FD), with a plan to expand to
            other entities.
          </p>
          <p>
            We are working with leading researchers in fibrous dysplasia and McCune–Albright syndrome at the
            International FD/MAS Consortium (Leiden University Medical Center), Sapienza University of Rome, and
            UCSF, alongside a Polish network of specialists. Individual reviewers will be acknowledged on the
            documents they review once the platform goes live.
          </p>
          <p className="about__contact">
            <Button variant="primary" onClick={() => window.open("mailto:kontakt@genequest.org")}>
              kontakt@genequest.org
            </Button>
          </p>
        </section>

        <section className="about__sec about__sec--cta">
          <div className="about__ctas">
            <a
              href="#/"
              className="about__cta"
              onClick={(e) => {
                e.preventDefault();
                onNav("/");
              }}
            >
              <span className="about__cta-label">
                {view === "parent" ? "Start with your disease" : "Start with a guideline document"}
              </span>
              <span className="about__cta-sub">
                {view === "parent"
                  ? "Find guidelines, doctors, and clinical trials."
                  : "Open living guidelines for a chosen entity."}
              </span>
              <span className="about__cta-arrow" aria-hidden>
                →
              </span>
            </a>
            <a
              href="#/doctors"
              className="about__cta"
              onClick={(e) => {
                e.preventDefault();
                onNav("/doctors");
              }}
            >
              <span className="about__cta-label">
                {view === "parent" ? "Find a doctor familiar with the disease" : "See the reviewer network"}
              </span>
              <span className="about__cta-sub">
                {view === "parent"
                  ? "Global directory, filterable by distance."
                  : "Doctors ranked by publication record and citation recency."}
              </span>
              <span className="about__cta-arrow" aria-hidden>
                →
              </span>
            </a>
            <a
              href="#/start-research"
              className="about__cta"
              onClick={(e) => {
                e.preventDefault();
                onNav("/start-research");
              }}
            >
              <span className="about__cta-label">Your disease isn't here yet?</span>
              <span className="about__cta-sub">Run the AI pipeline — first results in ~10 min.</span>
              <span className="about__cta-arrow" aria-hidden>
                →
              </span>
            </a>
          </div>
        </section>
      </article>
    </div>
  );
}
