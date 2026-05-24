/* GeneGuidelines — Banner for Kaggle Gemma 4 Good Hackathon jurors.
   Two states:
     • expanded  — full banner pinned above the product header (default).
     • collapsed — small floating pill in the top-right corner. Click → expand.
   State persists in localStorage and survives route changes; the collapsed
   pill renders on every route so judges always have one-tap access back in. */

import { useCallback, useEffect, useState, type MouseEvent } from "react";
import type { Route } from "../router/types";
import "./judges-banner.css";

const JB_STATE_KEY = "gg-judges-banner-state-v2";

const JB_LINKS = {
  snapshot: "https://kaggle-geneguidelines.genequest.org",
  snapshotAdmin: "https://kaggle-admin-geneguidelines.genequest.org",
  video: "https://www.youtube.com/watch?v=aMtnFdvQ3iA",
  writeup:
    "https://www.kaggle.com/competitions/gemma-4-good-hackathon/writeups/geneguidelines-living-clinical-guidelines-for-ra",
  repo: "https://github.com/GeneQuestOrg/GeneGuidelines/tree/kaggle-submission-2026-05-18",
};

type BannerState = "expanded" | "collapsed";

export interface JudgesBannerProps {
  route: Route;
  onNav: (path: string) => void;
}

interface JudgesBadgeProps {
  onExpand: () => void;
}

interface JudgesBannerExpandedProps {
  onNav: (path: string) => void;
  onCollapse: () => void;
  route: Route;
}

function useBannerState(): [BannerState, (state: BannerState) => void] {
  const [state, setState] = useState<BannerState>(() => {
    try {
      const v = localStorage.getItem(JB_STATE_KEY);
      if (v === "expanded" || v === "collapsed") return v;
    } catch {
      /* ignore localStorage errors */
    }
    return "expanded";
  });

  useEffect(() => {
    try {
      localStorage.setItem(JB_STATE_KEY, state);
    } catch {
      /* ignore localStorage errors */
    }
  }, [state]);

  return [state, setState];
}

export function JudgesBanner({ onNav, route }: JudgesBannerProps) {
  const [state, setState] = useBannerState();

  const collapse = useCallback(() => setState("collapsed"), [setState]);
  const expand = useCallback(() => {
    setState("expanded");
    /* If user isn't on home, banner is right at the top of the page,
       so scroll back up to show it. */
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  }, [setState]);

  if (state === "collapsed") {
    return <JudgesBadge onExpand={expand} />;
  }
  return <JudgesBannerExpanded onNav={onNav} onCollapse={collapse} route={route} />;
}

/* ── Collapsed: small floating pill ─────────────────────────────────── */
function JudgesBadge({ onExpand }: JudgesBadgeProps) {
  return (
    <button
      type="button"
      className="jb-badge"
      onClick={onExpand}
      aria-label="Re-open Kaggle juror note"
      title="Re-open juror note"
    >
      <span className="jb-badge__dot" aria-hidden></span>
      <span className="jb-badge__label">
        <span className="jb-badge__kicker">Kaggle</span>
        <span className="jb-badge__main">Juror note</span>
      </span>
      <span className="jb-badge__chev" aria-hidden>
        <svg viewBox="0 0 12 12" width="10" height="10">
          <path
            d="M3 4.5 L6 7.5 L9 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    </button>
  );
}

/* ── Expanded: full banner ──────────────────────────────────────────── */
function JudgesBannerExpanded({ onNav, onCollapse, route }: JudgesBannerExpandedProps) {
  const onHome = route.name === "home";

  const scrollToActiveResearch = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();
      if (!onHome) {
        onNav("/");
        /* Wait for home render, then scroll. */
        setTimeout(() => {
          const headings = document.querySelectorAll(".main h2, .main h3");
          for (const h of headings) {
            if (h.textContent && h.textContent.trim().toLowerCase().startsWith("active research")) {
              const top = h.getBoundingClientRect().top + window.scrollY - 80;
              window.scrollTo({ top, behavior: "smooth" });
              return;
            }
          }
        }, 120);
        return;
      }
      const headings = document.querySelectorAll(".main h2, .main h3");
      for (const h of headings) {
        if (h.textContent && h.textContent.trim().toLowerCase().startsWith("active research")) {
          const top = h.getBoundingClientRect().top + window.scrollY - 80;
          window.scrollTo({ top, behavior: "smooth" });
          return;
        }
      }
      window.scrollTo({ top: window.innerHeight, behavior: "smooth" });
    },
    [onHome, onNav],
  );

  const goToStartResearch = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();
      onNav("/start-research");
    },
    [onNav],
  );

  const goToFD = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();
      onNav("/diseases/fd");
    },
    [onNav],
  );

  return (
    <aside className="jb" role="complementary" aria-label="Note for Kaggle Gemma 4 Good Hackathon jurors">
      <div className="jb__inner">
        <header className="jb__head">
          <div className="jb__pill">
            <span className="jb__pill-dot" aria-hidden></span>
            <span className="jb__pill-text">Note for jurors</span>
          </div>
          <div className="jb__track">
            Kaggle <b>Gemma 4 Good Hackathon</b> <span aria-hidden>·</span> Health &amp; Sciences Track
          </div>
          <button
            type="button"
            className="jb__close"
            onClick={onCollapse}
            aria-label="Collapse juror note"
            title="Collapse"
          >
            <svg viewBox="0 0 14 14" width="12" height="12" aria-hidden>
              <path
                d="M3 8 L7 4 L11 8"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
            </svg>
            <span className="jb__close-label">Collapse</span>
          </button>
        </header>

        <div className="jb__lede">
          <p>
            This live environment is <b>actively evolving beyond our May 18 submission</b> to support
            ongoing clinical validation with researchers at <b>UCSF</b> and <b>Sapienza University</b>.
          </p>
          <a className="jb__snapshot" href={JB_LINKS.snapshot} target="_blank" rel="noopener noreferrer">
            <span className="jb__snapshot-icon" aria-hidden>
              <svg viewBox="0 0 16 16" width="14" height="14">
                <rect
                  x="2"
                  y="3"
                  width="12"
                  height="10"
                  rx="1.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.3"
                />
                <line x1="2" y1="6" x2="14" y2="6" stroke="currentColor" strokeWidth="1.3" />
                <circle cx="4.5" cy="4.5" r="0.6" fill="currentColor" />
              </svg>
            </span>
            View the frozen May 18 Kaggle Submission Snapshot
            <span className="jb__arrow" aria-hidden>
              ↗
            </span>
          </a>
          <a
            className="jb__snapshot-admin"
            href={JB_LINKS.snapshotAdmin}
            target="_blank"
            rel="noopener noreferrer"
          >
            Or peek into the snapshot admin · engine inspector
            <span className="jb__arrow" aria-hidden>
              ↗
            </span>
          </a>
        </div>

        <div className="jb__guide">
          <div className="jb__guide-label">How Gemma 4 powers GeneGuidelines</div>
          <ol className="jb__steps">
            <li>
              <span className="jb__num" aria-hidden>
                ①
              </span>
              <div className="jb__step-body">
                <div className="jb__step-title">Six parallel workflows per disease</div>
                <p className="jb__step-text">
                  <a href="#/start-research" onClick={goToStartResearch} className="jb__step-link">
                    Click <em>Add a disease</em>
                  </a>{" "}
                  to fan out six concurrent Gemma 4 workflows for a new entry: the consensus-paper
                  finder, the recruiting clinical trials extractor, the therapy-line classifier,
                  the specialist directory builder (PubMed authors → geo-resolved), the patient
                  foundations finder, and the long-form clinical guideline drafter. Every
                  recommendation anchored to a PMID.
                </p>
              </div>
            </li>
            <li>
              <span className="jb__num" aria-hidden>
                ②
              </span>
              <div className="jb__step-body">
                <div className="jb__step-title">Gemma 4 as a librarian for a heavier model</div>
                <p className="jb__step-text">
                  <a href="#active-research" onClick={scrollToActiveResearch} className="jb__step-link">
                    Scroll down to <em>Active research</em>
                  </a>{" "}
                  to follow live SSE traces. Gemma 4 reads each paper, extracts structured
                  fragments, and writes them into the graph the synthesis model later navigates —
                  cheap edge calls extract evidence, a frontier model reasons against the index.
                  Every reviewer decision is signed; the resulting corpus is rare on its own.
                </p>
              </div>
            </li>
            <li>
              <span className="jb__num" aria-hidden>
                ③
              </span>
              <div className="jb__step-body">
                <div className="jb__step-title">Privacy by data flow, not policy</div>
                <p className="jb__step-text">
                  <a href="#/diseases/fd" onClick={goToFD} className="jb__step-link">
                    Open the FD page → <em>Private case context</em>
                  </a>{" "}
                  and upload a discharge summary. Gemma 4 strips identifiers in-memory across
                  five PII categories (names, IDs, dates, addresses, contacts) and returns only
                  structured facts. The original bytes never reach disk — the audit badge proves
                  zero identifiers reached the synthesis model.
                </p>
              </div>
            </li>
          </ol>
        </div>

        <footer className="jb__foot">
          <a className="jb__link" href={JB_LINKS.video} target="_blank" rel="noopener noreferrer">
            <span aria-hidden className="jb__link-icon">
              ▶
            </span>
            Watch 3-min Video
          </a>
          <a className="jb__link" href={JB_LINKS.writeup} target="_blank" rel="noopener noreferrer">
            <span aria-hidden className="jb__link-icon">
              ✎
            </span>
            Read Kaggle Writeup
          </a>
          <a className="jb__link" href={JB_LINKS.repo} target="_blank" rel="noopener noreferrer">
            <span aria-hidden className="jb__link-icon">
              ⌥
            </span>
            GitHub Repo
          </a>
        </footer>
      </div>
    </aside>
  );
}
