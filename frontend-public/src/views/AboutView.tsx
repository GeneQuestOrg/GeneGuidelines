import { Button } from "@gene-guidelines/ui";
import type { AudienceView } from "../router/types";
import "./about-view.css";

export interface AboutViewProps {
  view: AudienceView;
  onNav: (path: string) => void;
}

interface AboutTocItem {
  id: string;
  label: string;
  indent?: boolean;
}

const ABOUT_TOC: AboutTocItem[] = [
  { id: "top", label: "Why we built this" },
  { id: "origins", label: "Origins" },
  { id: "scale", label: "Scale" },
  { id: "specialist", label: "Why a specialist isn't enough" },
  { id: "families", label: "For families", indent: true },
  { id: "clinicians", label: "For clinicians", indent: true },
  { id: "disease-page", label: "One page per disease" },
  { id: "how", label: "How it works" },
  { id: "privacy", label: "Privacy" },
  { id: "not", label: "What this is not" },
  { id: "limitations", label: "Limitations" },
  { id: "about", label: "Who is behind this" },
];

function scrollToAboutSection(sectionId: string): void {
  document.getElementById(sectionId)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function AboutTocLinks() {
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
            {item.label}
          </a>
        </li>
      ))}
    </ul>
  );
}

function AboutTableOfContents() {
  return (
    <nav className="about__toc" aria-label="On this page">
      <details className="about__toc-collapse">
        <summary className="about__toc-summary">On this page</summary>
        <AboutTocLinks />
      </details>
      <div className="about__toc-desktop">
        <div className="about__toc-label">On this page</div>
        <AboutTocLinks />
      </div>
    </nav>
  );
}

export function AboutView({ onNav }: AboutViewProps) {
  return (
    <div className="page page--about">
      <header id="top" className="about__hero">
        <div className="about__eyebrow">Why we built this</div>
        <div className="about__eyebrow-sub">8 min read · use the section links to jump around</div>
        <h1 className="about__lead">
          PubMed indexes on the order of <b>10,000</b> new articles on rare diseases every year — tens added every
          day.
          <br />
          Most of those diseases are tracked by a handful of researchers worldwide — rarely the doctor a family
          actually has access to.
          <br />
          GeneGuidelines exists to make that flow of knowledge usable at the point of care.
        </h1>
        <p className="about__hero-tldr">
          A living clinical guideline per rare disease — every claim cited to a PMID, every AI-proposed change
          reviewed and rated by a clinician. Open source. Free, no ads, no account required.
        </p>
      </header>

      <div className="about__layout">
        <AboutTableOfContents />

        <article className="about__article">
          <section id="origins" className="about__sec">
            <h2 className="about__h2">A note on origins</h2>
            <p>The project began with two separate failures of the same kind.</p>
            <p>
              A rapidly growing bone lesion in a child&apos;s craniofacial skeleton, found incidentally during a
              routine dental check-up, was biopsied and read as juvenile trabecular ossifying fibroma — a diagnosis
              whose standard of care is extensive surgery. The histopathologist worked carefully and listed fibrous
              dysplasia in the differential; she ordered MDM2 FISH to rule out a low-grade osteosarcoma. GNAS
              sequencing — the test that distinguishes JTOF from the actual diagnosis per current literature — was
              not among those run. The family ordered it privately. The diagnosis changed.
            </p>
            <p>
              That should have ended it. It did not. A senior craniofacial surgeon abroad, informed of the corrected
              diagnosis, still proposed to curette the lesion — a procedure the international consensus on fibrous
              dysplasia in children explicitly advises against in the absence of pain or functional compromise. Two
              other surgeons also considered excision on the first visit and revised their recommendation on the
              second. Only one specialist — found by the family through a manual PubMed search for domestic authors
              writing on the disease — read the consensus from the start.
            </p>
            <p>
              None of these doctors were incompetent. The histopathologist worked with care; the surgeon abroad has a
              world-class record in his field. No one can hold the specifics of every rare disease in working memory,
              and there is no reason they should. The corrected plan arrived only because the family had the
              resources, the language, and the contacts to keep looking after every authoritative answer it received
              — and the kindness of a few people along the way who were paying attention.
            </p>
            <p>
              This is not a problem of individual errors. It is a systemic problem of scale. A good outcome should not
              rest on this kind of luck.
            </p>
          </section>

          <section id="scale" className="about__sec">
            <h2 className="about__h2">Scale of the problem</h2>

            <div className="about__stats">
              <div className="about__stat">
                <div className="about__stat-num">~300 M</div>
                <div className="about__stat-label">
                  People worldwide living with a rare disease at any given time. About <b>80%</b> have a genetic
                  cause; of those, roughly <b>70%</b> present in childhood.
                  <span className="about__cite">
                    (
                    <a
                      href="https://www.nature.com/articles/s41431-019-0508-0"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Nguengang Wakap et al., Eur J Hum Genet 2020
                    </a>
                    ;{" "}
                    <a
                      href="https://www.thelancet.com/journals/langlo/article/PIIS2214-109X(24)00056-1/fulltext"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Lancet Global Health, 2024
                    </a>
                    )
                  </span>
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">~7,000</div>
                <div className="about__stat-label">
                  Rare diseases described in OMIM and Orphanet. Most have fewer than 100 publications per year.
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">~1.5 M</div>
                <div className="about__stat-label">
                  New publications indexed by PubMed every year
                  <span className="about__cite">
                    (
                    <a
                      href="https://www.nlm.nih.gov/bsd/medline_pubmed_production_stats.html"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      NLM, FY2023
                    </a>
                    ).
                  </span>{" "}
                  Tens of those are on rare diseases each day — on the order of ten thousand a year, spread across
                  thousands of distinct entities.
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">~9 years</div>
                <div className="about__stat-label">
                  Median lag from new evidence to its incorporation into a formal clinical guideline.
                  <span className="about__cite">
                    (Berg et al., Surgery 2025,{" "}
                    <a
                      href="https://pubmed.ncbi.nlm.nih.gov/39592333/"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      PMID 39592333
                    </a>
                    )
                  </span>
                </div>
              </div>
              <div className="about__stat">
                <div className="about__stat-num">~4.8 years</div>
                <div className="about__stat-label">
                  Average time from symptom onset to an accurate diagnosis of a rare disease.
                  <span className="about__cite">
                    (
                    <a
                      href="https://www.thelancet.com/journals/langlo/article/PIIS2214-109X(24)00056-1/fulltext"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Lancet Global Health, 2024
                    </a>
                    )
                  </span>
                </div>
              </div>
            </div>

            <p>
              The point was made plainly at a Polish rare-disease conference in 2026: no family doctor can stay
              current on every rare disease they might encounter. The literature does not allow it — and most
              specialists have the same problem one disease over.
            </p>
          </section>

          <section id="specialist" className="about__sec">
            <h2 className="about__h2">Why &quot;a specialist&quot; is not enough</h2>

            <h3 id="families" className="about__h3">
              For families
            </h3>
            <p>
              Hearing <em>&quot;we&apos;ll refer you to a maxillofacial surgeon&quot;</em> is a good referral. But a
              maxillofacial surgeon with a world-class record in orthognathic surgery has not necessarily seen a child
              with fibrous dysplasia. The two competencies sit on different axes — and finding someone with hands-on
              experience in the specific disease usually takes more effort than a single referral provides. Clinical
              experience in a rare disease is concentrated in a narrow set of centres, and locating them takes active
              work.
            </p>
            <p>
              None of this is about distrust of doctors. It is about realism. A 15-minute appointment, a packed
              schedule, dozens of unrelated patients in a single day — these are the conditions under which medicine
              actually happens. In a rare disease, no one will follow your child&apos;s specific case as closely as
              you will. That is not a criticism of any doctor; it is the arithmetic of the job, and the reason the
              family has to take an active part.
            </p>
            <p>
              Each disease page on GeneGuidelines is built for that role: a <b>checklist for the conversation in the
              consulting room</b> — what tests have been done, what should come next, what red flags to watch for,
              which specialist centres are active. You bring it; your doctor stays in charge of the decision.
            </p>
            <p>You can help your family doctor in two concrete ways:</p>
            <ol className="about__steps">
              <li>
                <b>Bring them materials.</b> Each disease section includes a short, curated set of peer-reviewed
                articles for the primary-care doctor — ready to print or email. A 30-minute read.
              </li>
              <li>
                <b>Or point them at the guideline document.</b> Each disease has a <em>living guideline</em> — an
                AI-drafted, fully-cited summary of the official guidelines and the literature that clinicians can
                rate and flag; nobody officially signs off on it. The same text an expert in Leiden or Rome would
                read.
              </li>
            </ol>

            <h3 id="clinicians" className="about__h3">
              For clinicians
            </h3>
            <p>
              Clinical specialisation does not scale linearly with the number of diagnosed diseases. The specifics of a
              rare entity often need hundreds of published cases that would take weeks to read, regardless of
              seniority. This is not a competence problem — it is an attention-distribution problem.
            </p>
            <p>GeneGuidelines is built for both sides of that asymmetry:</p>
            <ul className="about__bullets">
              <li>
                <b>If you are seeing a patient with a disease rarely present in your practice</b> — open the
                guideline document for that entity. Current state of clinical knowledge, citations to original
                publications, provenance for every recommendation (who approved it and when).
              </li>
              <li>
                <b>If you are a specialist in a given disease</b> — you can join as a reviewer. The AI Watcher
                analyses new publications and proposes updates on a rolling basis; you rate each one{" "}
                <em>useful / not useful</em> and can leave a note — a few minutes&apos; work. Your signal, weighted
                by your verified experience, ranks the suggestion for the next clinician who reads it.
              </li>
            </ul>
          </section>

          <section id="disease-page" className="about__sec">
            <h2 className="about__h2">One page per disease — more than guidelines</h2>
            <p>Each disease in the catalogue surfaces in a single layout:</p>
            <ul className="about__bullets">
              <li>
                A <b>living guideline</b> — paragraph-anchored, every claim backed by a PMID, every change signed.
              </li>
              <li>
                A <b>decision pathway</b> for the family — symptom → test → specialist → next step, rendered as a
                flowchart rather than a wall of text.
              </li>
              <li>
                A <b>specialist directory</b> — ranked by publication record, citation recency, and whether the
                doctor cites the current consensus in their own recent work.
              </li>
              <li>
                <b>Active clinical trials</b> — phase, location, enrollment status, contact.
              </li>
              <li>
                <b>Therapy lines</b> — labelled by evidence tier (consensus / verified / pending / preclinical).
              </li>
              <li>
                <b>Patient foundations</b> supporting that disease, where they exist. An engaged foundation can carry
                real weight for a family in diagnosis — and these are not easy to find from outside the community. The
                catalogue surfaces what exists, even when only one organisation worldwide works on a disease.
              </li>
              <li>
                A <b>private case-context panel</b> — paste a discharge summary or pathology report and get custom
                research for <em>your</em> case. Gemma 4 strips the identifiers on the operator&apos;s infrastructure
                first, so nothing personal leaves the building.
              </li>
            </ul>
            <p>
              The catalogue is demand-driven. It started with fibrous dysplasia, McCune–Albright syndrome, and Noonan
              syndrome; any visitor can request a new disease through a public form, which fans out six AI workflows
              in parallel for that disease.
            </p>
          </section>

          <section id="how" className="about__sec">
            <h2 className="about__h2">How it works</h2>
            <p>
              This is not another medical chatbot. The platform is built on reproducible, reviewable workflows where
              every recommendation is anchored to a PMID and every change is signed by a clinician.
            </p>
            <p>
              It runs on <b>Gemma 4</b>, an open model. The strength is not a bigger model — it is prompt engineering
              grounded in real diagnostic journeys (like the one above), and a system that sharpens with every
              clinician rating and anonymised family case it sees. Per-disease fine-tuning on that accumulating signal
              is on the roadmap.
            </p>
            <p>
              Two layers run side by side. <b>Official consensus</b> — where one exists (e.g. Boyce et al. 2019 for
              FD/MAS) — is the ground truth. Alongside it, a <b>living layer</b> evolves with new publications,
              proposing targeted updates that specialists rate, so the most useful ones rise to the top.
            </p>
            <ol className="about__pipeline">
              <li>
                <span className="about__pipeline-num">01</span>
                <div>
                  <b>Watcher.</b> Scans PubMed routinely, per disease. Categorises publication type — case report,
                  original research, review, consensus.
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">02</span>
                <div>
                  <b>Evaluator.</b> Decides whether the new evidence is strong enough to modify an existing
                  recommendation. Most publications do not warrant an update, and the system is allowed to say so.
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">03</span>
                <div>
                  <b>Proposal.</b> If a change is warranted, the AI proposes one — a diff against a specific
                  paragraph, with citations, rationale, and an evidence-strength score.
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">04</span>
                <div>
                  <b>Clinician signal.</b> Clinicians rate the proposal <em>useful / not useful</em> and can leave a
                  note. It is a signal for the next clinician who reads it — &quot;two of three found this
                  useful&quot; — weighted by the reviewer&apos;s verified experience.
                </div>
              </li>
              <li>
                <span className="about__pipeline-num">05</span>
                <div>
                  <b>Ranking &amp; surfacing.</b> Suggestions rise or fall by that weighted signal. A low-risk,
                  well-supported one can surface to families as &quot;worth discussing with your doctor&quot;;
                  higher-stakes items stay in the expert view.
                </div>
              </li>
            </ol>
          </section>

          <section id="privacy" className="about__sec">
            <h2 className="about__h2">Privacy is an architectural property, not a policy</h2>
            <p>
              The case-context panel accepts free text — a discharge summary, a biopsy report. The text is read into a
              single request handler&apos;s memory, hashed (SHA-256) for deduplication, and passed to a redaction model
              — <b>Gemma 4</b>, an open model that can run entirely on the operator&apos;s own hardware —
              running on the operator&apos;s infrastructure. Only a structured payload — facts without identifiers —
              flows downstream. The raw bytes are discarded explicitly: not written to disk, not present in any
              backup.
            </p>
            <p>
              The UI shows a categorical breakdown of what was stripped (names, government IDs, absolute dates,
              addresses, contact details) before any further step runs. Zero personal identifiers reach the synthesis
              model — not as a promise, as a property of the data flow.
            </p>
          </section>

          <section id="not" className="about__sec">
            <h2 className="about__h2">What this is not</h2>
            <div className="about__nots">
              <div className="about__not">
                <h3>Not a diagnostic tool</h3>
                <p>
                  You do not enter symptoms or test results here. The system operates at the level of guidelines for
                  an already-diagnosed disease.
                </p>
              </div>
              <div className="about__not">
                <h3>Not a retrieval chatbot</h3>
                <p>
                  Every recommendation is anchored to a PMID. Every AI-proposed change is reviewed and rated by
                  clinicians before it carries any weight. The synthesis model works against an indexed corpus
                  assembled paragraph by paragraph — never against free-form prompts over a pile of papers.
                </p>
              </div>
              <div className="about__not">
                <h3>Not a substitute for consultation</h3>
                <p>
                  Material here contributes to clinical discussion, not to individual recommendations. Every
                  therapeutic decision belongs to the attending physician.
                </p>
              </div>
              <div className="about__not">
                <h3>Not a commercial product</h3>
                <p>
                  Built by the GeneQuest Foundation (KRS 0001211461). Open source — see{" "}
                  <a
                    href="https://github.com/GeneQuestOrg/GeneGuidelines"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="about__link"
                  >
                    github.com/GeneQuestOrg/GeneGuidelines
                  </a>
                  . No ads, no paywall, no monetised API.
                </p>
              </div>
            </div>
          </section>

          <section id="limitations" className="about__sec">
            <h2 className="about__h2">What we don&apos;t know and don&apos;t do</h2>
            <ul className="about__bullets about__bullets--candid">
              <li>
                <b>Disease coverage is partial.</b> A new entity needs a baseline document and, ideally, at least one
                specialist reviewer before its guideline stabilises. The demand-driven pipeline produces a first
                draft; the long tail of validation takes longer.
              </li>
              <li>
                <b>The doctor directory is built from PubMed.</b> Publication activity is a decent proxy for
                scientific engagement — not a complete picture of clinical competence. An excellent practitioner who
                does not publish may be missed. Please report gaps.
              </li>
              <li>
                <b>AI proposals can be over-optimistic.</b> Every draft is filtered by a reviewer before publication,
                but subtle errors may still slip through. Any approved paragraph can be challenged at any time.
              </li>
              <li>
                <b>Translations are uneven.</b> Some literature is English-only; some documents currently exist in a
                single language. Multilingual coverage is a slow, ongoing piece of work.
              </li>
            </ul>
          </section>

          <section id="about" className="about__sec about__sec--who">
            <h2 className="about__h2">Who is behind this</h2>
            <p>
              <b>GeneQuest Foundation</b> — a Polish non-profit focused on knowledge infrastructure for rare genetic
              diseases. KRS 0001211461. Starting point: fibrous dysplasia, expanding to other entities on demand.
            </p>
            <p>
              Two specialists working on fibrous dysplasia and McCune–Albright syndrome have agreed to be among the
              first to test the platform — one at Sapienza University of Rome, one at UCSF. One of them has also
              offered to advise on pitfalls he has seen in clinical AI applications elsewhere. From there, we are
              building toward a wider reviewer network. Individual reviewers will be acknowledged on the documents
              they review as the catalogue grows.
            </p>
            <p className="about__contact">
              <Button variant="primary" onClick={() => window.open("mailto:kontakt@genequest.org")}>
                kontakt@genequest.org
              </Button>
            </p>
          </section>

          <section className="about__sec about__sec--cta">
            <h2 className="about__h2 about__h2--cta">Where to go next</h2>
            <div className="about__ctas">
              <a
                href="/"
                className="about__cta"
                onClick={(e) => {
                  e.preventDefault();
                  onNav("/");
                }}
              >
                <span className="about__cta-label">Start with your disease</span>
                <span className="about__cta-sub">Guidelines, doctors, trials, decision pathway.</span>
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
                <span className="about__cta-label">Find a doctor familiar with the disease</span>
                <span className="about__cta-sub">
                  Global directory, filterable by distance and by whether the doctor cites the current consensus.
                </span>
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
                <span className="about__cta-label">Your disease isn&apos;t here yet?</span>
                <span className="about__cta-sub">
                  Run the AI pipeline — first results in about ten minutes.
                </span>
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
