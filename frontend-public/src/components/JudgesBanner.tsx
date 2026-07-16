/* GeneGuidelines — Banner for Kaggle Gemma 4 Good Hackathon jurors.
   Three states (see ./judgesBannerState.ts for the machine):
     • ribbon    — full-width single line above the product header (default).
     • expanded  — full juror panel. Default for judges arriving via ?from=kaggle.
     • pill       — small floating badge in the top-right corner.
   Explicit user actions persist in localStorage and survive route changes;
   the pill renders on every route so judges always have one-tap access back. */

import { useCallback, useState, type MouseEvent } from "react";
import type { Route } from "../router/types";
import {
  JB_SESSION_FROM_KAGGLE_KEY,
  JB_STATE_KEY,
  resolveInitialState,
  shouldRememberKaggleSession,
  type BannerState,
} from "./judgesBannerState";
import "./judges-banner.css";

const JB_LINKS = {
  snapshot: "https://kaggle-geneguidelines.genequest.org",
  snapshotAdmin: "https://kaggle-admin-geneguidelines.genequest.org",
  video: "https://www.youtube.com/watch?v=aMtnFdvQ3iA",
  writeup:
    "https://www.kaggle.com/competitions/gemma-4-good-hackathon/writeups/geneguidelines-living-clinical-guidelines-for-ra",
  repo: "https://github.com/GeneQuestOrg/GeneGuidelines/tree/kaggle-submission-2026-05-18",
};

export interface JudgesBannerProps {
  route: Route;
  onNav: (path: string) => void;
  /** True when the current hash carries `?from=kaggle` (judges' submission link). */
  fromKaggle?: boolean;
}

interface JudgesRibbonProps {
  onExpand: () => void;
  onDismiss: () => void;
}

interface JudgesBadgeProps {
  onExpand: () => void;
}

interface JudgesBannerExpandedProps {
  onNav: (path: string) => void;
  onCollapse: () => void;
  onDismiss: () => void;
  route: Route;
}

function readStored(): string | null {
  try {
    return localStorage.getItem(JB_STATE_KEY);
  } catch {
    return null;
  }
}

function readSessionFromKaggle(): boolean {
  try {
    return sessionStorage.getItem(JB_SESSION_FROM_KAGGLE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Resolves the initial state once, then tracks explicit user actions
    (which persist) for the rest of the session. */
function useBannerState(fromKaggle: boolean): [BannerState, (state: BannerState) => void] {
  const [state, setState] = useState<BannerState>(() => {
    const stored = readStored();
    /* Remember a ?from=kaggle arrival so hash navigation keeps it expanded. */
    if (shouldRememberKaggleSession(stored, fromKaggle)) {
      try {
        sessionStorage.setItem(JB_SESSION_FROM_KAGGLE_KEY, "1");
      } catch {
        /* ignore sessionStorage errors */
      }
    }
    return resolveInitialState({
      stored,
      fromKaggle,
      sessionFromKaggle: readSessionFromKaggle(),
    });
  });

  const setStateAndPersist = useCallback((next: BannerState) => {
    setState(next);
    /* An explicit action is a deliberate choice — persist it so it outlasts
       the link param on subsequent visits. */
    try {
      localStorage.setItem(JB_STATE_KEY, next);
    } catch {
      /* ignore localStorage errors */
    }
  }, []);

  return [state, setStateAndPersist];
}

export function JudgesBanner({ onNav, route, fromKaggle = false }: JudgesBannerProps) {
  const [state, setState] = useBannerState(fromKaggle);

  const dismiss = useCallback(() => setState("pill"), [setState]);
  const collapseToRibbon = useCallback(() => setState("ribbon"), [setState]);
  const expand = useCallback(() => {
    setState("expanded");
    /* If user isn't on home, banner is right at the top of the page,
       so scroll back up to show it. */
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  }, [setState]);

  if (state === "pill") {
    return <JudgesBadge onExpand={expand} />;
  }
  if (state === "ribbon") {
    return <JudgesRibbon onExpand={expand} onDismiss={dismiss} />;
  }
  return (
    <JudgesBannerExpanded
      onNav={onNav}
      onCollapse={collapseToRibbon}
      onDismiss={dismiss}
      route={route}
    />
  );
}

/* ── Ribbon: full-width single line, default state ──────────────────── */
function JudgesRibbon({ onExpand, onDismiss }: JudgesRibbonProps) {
  const dismiss = useCallback(
    (e: MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      onDismiss();
    },
    [onDismiss],
  );

  return (
    <div className="jb-ribbon">
      <button
        type="button"
        className="jb-ribbon__main"
        onClick={onExpand}
        aria-expanded={false}
        aria-label="Open the Kaggle juror note: deadline-day snapshot and judge guide"
      >
        <span className="jb-ribbon__icon" aria-hidden>
          🏆
        </span>
        <span className="jb-ribbon__text">
          <b>Kaggle Gemma Hackathon entry</b>
          <span className="jb-ribbon__sep" aria-hidden>
            ·
          </span>
          see the deadline-day snapshot &amp; judge guide
        </span>
        <span className="jb-ribbon__arrow" aria-hidden>
          →
        </span>
      </button>
      <button
        type="button"
        className="jb-ribbon__close"
        onClick={dismiss}
        aria-label="Dismiss the Kaggle juror note"
        title="Dismiss"
      >
        <svg viewBox="0 0 14 14" width="11" height="11" aria-hidden>
          <path
            d="M3.5 3.5 L10.5 10.5 M10.5 3.5 L3.5 10.5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
      </button>
    </div>
  );
}

/* ── Pill: small floating badge ─────────────────────────────────────── */
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
function JudgesBannerExpanded({ onNav, onCollapse, onDismiss, route }: JudgesBannerExpandedProps) {
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
          <div className="jb__controls">
            <button
              type="button"
              className="jb__close"
              onClick={onCollapse}
              aria-expanded
              aria-label="Collapse juror note to a one-line ribbon"
              title="Collapse to ribbon"
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
            <button
              type="button"
              className="jb__dismiss"
              onClick={onDismiss}
              aria-label="Dismiss juror note to a floating badge"
              title="Dismiss"
            >
              <svg viewBox="0 0 14 14" width="12" height="12" aria-hidden>
                <path
                  d="M3.5 3.5 L10.5 10.5 M10.5 3.5 L3.5 10.5"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  fill="none"
                />
              </svg>
            </button>
          </div>
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
                  <a href="/start-research" onClick={goToStartResearch} className="jb__step-link">
                    Click <em>Start research</em>
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
                  <a href="/diseases/fd" onClick={goToFD} className="jb__step-link">
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
          <button
            type="button"
            className="jb__close jb__close--bottom"
            onClick={onCollapse}
            aria-expanded
            aria-label="Collapse juror note to a one-line ribbon"
            title="Collapse to ribbon"
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
        </footer>
      </div>
    </aside>
  );
}
