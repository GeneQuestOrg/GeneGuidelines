/** Stub disease page — a rare disease that exists in the Tier-1 index but has
 * never been researched (no content record, no localSlug). Resolved 100%
 * client-side from the index (``api/diseaseStub.ts``); shows the real index
 * facts, a skeleton of what a research run will produce, curated public
 * sources, and a single "Run research" call to action.
 *
 * Honesty note (this is a medical product): the page never implies the content
 * is expert-approved. Status is "not researched yet"; the consent text states
 * the result is an unverified AI draft with citations that does not replace
 * medical advice. External links are only rendered when their identifier
 * actually exists — no fabricated OMIM/ORPHA/NBK ids.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, Section } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import {
  bootstrapDisease,
  type BootstrapDiseaseRequest,
} from "../api/bootstrapDisease";
import { DEFAULT_GUIDELINE_PROFILE } from "../api/guidelineRun";
import { resolveDiseaseStub, type DiseaseStubMeta } from "../api/diseaseStub";
import { useActiveResearchRuns } from "../hooks/useActiveResearchRuns";
import "../styles/disease-page.css";
import "../styles/research.css";
import "../styles/disease-stub.css";

export interface DiseaseStubViewProps {
  slug: string;
  onNav: (path: string) => void;
  notFound: ReactNode;
}

type StubState =
  | { kind: "loading" }
  | { kind: "notfound" }
  | { kind: "ready"; meta: DiseaseStubMeta };

/* ── inline skeleton-card icons (copied from drafty-ui/draft14) ───────────── */
const iconGuideline: ReactNode = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <line x1="9" y1="8" x2="15" y2="8" />
    <line x1="9" y1="12" x2="15" y2="12" />
    <line x1="9" y1="16" x2="13" y2="16" />
  </svg>
);
const iconDoctors: ReactNode = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="8" r="3.4" />
    <path d="M5.5 20c0-3.4 2.9-6 6.5-6s6.5 2.6 6.5 6" />
  </svg>
);
const iconTrials: ReactNode = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 3h4M11 3v6l-4.5 8.5A2 2 0 0 0 8.3 21h7.4a2 2 0 0 0 1.8-3.5L13 9V3" />
  </svg>
);
const iconTherapies: ReactNode = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="8.5" width="18" height="7" rx="3.5" />
    <line x1="12" y1="8.5" x2="12" y2="15.5" />
  </svg>
);
const iconFoundations: ReactNode = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 21V9l8-5 8 5v12" />
    <line x1="4" y1="21" x2="20" y2="21" />
    <line x1="9" y1="21" x2="9" y2="14" />
    <line x1="15" y1="21" x2="15" y2="14" />
  </svg>
);
const iconConsensus: ReactNode = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M7 3h10v16l-5-3-5 3V3z" />
    <path d="M9.5 9.5l1.5 1.5 3-3.5" />
  </svg>
);

const MONOGRAM_STOP = new Set([
  "of", "and", "the", "de", "du", "di", "da", "for", "with", "a", "an",
]);

/** Decorative monogram for the abbr tile — uppercase initials of up to 3
 * significant words, max 4 chars. Not authoritative. */
function monogram(name: string): string {
  const words = name.split(/[\s\-–—/]+/).filter(Boolean);
  const significant = words.filter((w) => !MONOGRAM_STOP.has(w.toLowerCase()));
  const picked = (significant.length > 0 ? significant : words).slice(0, 3);
  const mono = picked
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase()
    .slice(0, 4);
  return mono || name.slice(0, 2).toUpperCase();
}

/** Keep a ``<meta name="robots" content="noindex, follow">`` in the head while
 * this stub is mounted, restoring any prior value on unmount. A stub carries no
 * verified content, so it must not be indexed until the first research run. */
function useNoindex(): void {
  useEffect(() => {
    if (typeof document === "undefined") return;
    const head = document.head;
    const existing = head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const created = existing == null;
    const prevContent = existing?.getAttribute("content") ?? null;
    const el = existing ?? document.createElement("meta");
    if (created) {
      el.setAttribute("name", "robots");
      head.appendChild(el);
    }
    el.setAttribute("content", "noindex, follow");
    return () => {
      if (created) {
        el.remove();
      } else if (prevContent != null) {
        el.setAttribute("content", prevContent);
      } else {
        el.removeAttribute("content");
      }
    };
  }, []);
}

export function DiseaseStubView({ slug, onNav, notFound }: DiseaseStubViewProps) {
  const { t } = useTranslation("disease-stub");
  const [stub, setStub] = useState<StubState>({ kind: "loading" });
  const [consent, setConsent] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 50 = the active-research endpoint cap, so this disease's run is not missed
  // even when several diseases process at once (see DiseaseView).
  const { runs: activeRuns } = useActiveResearchRuns(50);

  useNoindex();

  useEffect(() => {
    // No synchronous setState here (react-hooks/set-state-in-effect): the view
    // is keyed by slug in DiseaseView, so a slug change remounts it fresh in the
    // "loading" state. The resolve result is applied from the async callback.
    let cancelled = false;
    void resolveDiseaseStub(slug).then((meta) => {
      if (cancelled) return;
      if (meta == null) {
        setStub({ kind: "notfound" });
        return;
      }
      // The index already links this to a real content record — send the user
      // to the full disease page. The `!== slug` guard avoids a redirect loop.
      if (meta.hasLocalRecord && meta.localSlug && meta.localSlug !== slug) {
        onNav(`/diseases/${encodeURIComponent(meta.localSlug)}`);
        return; // stay in "loading" until navigation unmounts this view
      }
      setStub({ kind: "ready", meta });
    });
    return () => {
      cancelled = true;
    };
  }, [slug, onNav]);

  const meta = stub.kind === "ready" ? stub.meta : null;
  const bootstrapSlug = meta ? meta.localSlug ?? meta.slug : null;
  const activeRun =
    bootstrapSlug != null
      ? activeRuns.find((r) => r.diseaseSlug === bootstrapSlug) ?? null
      : null;

  const runResearch = useCallback(async () => {
    if (!meta || busy || !consent) return;
    const body: BootstrapDiseaseRequest = {
      slug: meta.localSlug ?? meta.slug,
      name: meta.canonicalName,
      name_short: meta.canonicalName.slice(0, 24),
    };
    if (meta.omim) body.omim = meta.omim;
    if (meta.gene) body.gene = meta.gene;
    if (meta.inheritance) body.inheritance = meta.inheritance;
    if (meta.summary) body.summary = meta.summary;
    if (DEFAULT_GUIDELINE_PROFILE != null) body.profile = DEFAULT_GUIDELINE_PROFILE;

    setBusy(true);
    setError(null);
    try {
      const { execution_id } = await bootstrapDisease(body);
      const q = `?name=${encodeURIComponent(meta.canonicalName)}&disease=${encodeURIComponent(body.slug)}`;
      onNav(`/research/${encodeURIComponent(execution_id)}${q}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setError(t("errorUnauthorized"));
      } else if (e instanceof ApiRequestError && e.status === 409) {
        setError(e.message || t("errorQueueFull"));
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError(t("errorGeneric"));
      }
      setBusy(false);
    }
  }, [meta, busy, consent, onNav, t]);

  const onCtaClick = useCallback(() => {
    if (activeRun) {
      onNav(`/research/${encodeURIComponent(activeRun.runId)}`);
      return;
    }
    void runResearch();
  }, [activeRun, onNav, runResearch]);

  const skelCards = useMemo(
    () => [
      {
        key: "guideline",
        wide: true,
        icon: iconGuideline,
        name: t("skelGuidelineName"),
        badge: t("skelGuidelineBadge"),
        sub: t("skelGuidelineSub"),
        lines: ["w90", "w70", "w90", "w55"],
      },
      {
        key: "doctors",
        wide: false,
        icon: iconDoctors,
        name: t("skelDoctorsName"),
        badge: t("skelBadgeFast"),
        sub: null,
        lines: ["w70", "w40", "w55"],
      },
      {
        key: "trials",
        wide: false,
        icon: iconTrials,
        name: t("skelTrialsName"),
        badge: t("skelBadgeFast"),
        sub: null,
        lines: ["w90", "w55", "w40"],
      },
      {
        key: "therapies",
        wide: false,
        icon: iconTherapies,
        name: t("skelTherapiesName"),
        badge: t("skelBadgeFast"),
        sub: null,
        lines: ["w70", "w90", "w40"],
      },
      {
        key: "foundations",
        wide: false,
        icon: iconFoundations,
        name: t("skelFoundationsName"),
        badge: t("skelBadgeFast"),
        sub: null,
        lines: ["w55", "w70"],
      },
      {
        key: "consensus",
        wide: true,
        icon: iconConsensus,
        name: t("skelConsensusName"),
        badge: t("skelBadgeFast"),
        sub: t("skelConsensusSub"),
        lines: ["w90", "w40"],
      },
    ],
    [t],
  );

  if (stub.kind === "loading") {
    return (
      <section className="page page--disease page--stub" aria-busy="true">
        <div className="stub-loading" aria-label={t("loadingLabel")}>
          <div className="stub-loading__line w40" />
          <div className="stub-loading__line w90" />
          <div className="stub-loading__line w70" />
        </div>
      </section>
    );
  }

  if (stub.kind === "notfound") {
    return <>{notFound}</>;
  }

  const m = stub.meta;

  const facts: Array<{ key: string; label: string; value: ReactNode }> = [];
  if (m.gene) facts.push({ key: "gene", label: t("factGene"), value: <code>{m.gene}</code> });
  if (m.omim) facts.push({ key: "omim", label: t("factOmim"), value: <code>{m.omim}</code> });
  if (m.orphaCode)
    facts.push({
      key: "orpha",
      label: t("factOrphanet"),
      value: <code>{t("orphaValue", { code: m.orphaCode })}</code>,
    });
  if (m.inheritance)
    facts.push({ key: "inheritance", label: t("factInheritance"), value: m.inheritance });
  facts.push({ key: "status", label: t("factStatus"), value: t("statusFactValue") });

  const extCards: Array<{ key: string; src: string; title: string; id: string; href: string }> = [];
  if (m.omim) {
    extCards.push({
      key: "omim",
      src: t("extOmimSrc"),
      title: m.canonicalName,
      id: t("extOmimId", { omim: m.omim }),
      href: m.omimUrl ?? `https://www.omim.org/entry/${m.omim}`,
    });
  }
  if (m.orphaCode) {
    extCards.push({
      key: "orphanet",
      src: t("extOrphanetSrc"),
      title: m.canonicalName,
      id: t("extOrphanetId", { code: m.orphaCode }),
      href: m.orphaUrl ?? `https://www.orpha.net/en/disease/detail/${m.orphaCode}`,
    });
  }
  extCards.push({
    key: "trials",
    src: t("extTrialsSrc"),
    title: t("extTrialsTitle"),
    id: t("extTrialsId", { name: m.canonicalName }),
    href: `https://clinicaltrials.gov/search?cond=${encodeURIComponent(m.canonicalName)}&aggFilters=status:rec`,
  });
  extCards.push({
    key: "genereviews",
    src: t("extGeneReviewsSrc"),
    title: m.canonicalName,
    id: t("extGeneReviewsId"),
    href: `https://www.ncbi.nlm.nih.gov/books/?term=${encodeURIComponent(m.canonicalName)}`,
  });

  const ctaLabel = activeRun
    ? t("ctaViewRunning")
    : busy
      ? t("ctaButtonBusy")
      : t("ctaButton");
  const ctaDisabled = activeRun ? false : !consent || busy;

  return (
    <section className="page page--disease page--stub">
      {/* HERO — real index metadata (exists before any research) */}
      <div className="d-hero">
        <div className="d-hero__top">
          <div className="d-hero__abbr">{monogram(m.canonicalName)}</div>
          <div className="d-hero__title-block">
            <h1 className="d-hero__name">{m.canonicalName}</h1>
          </div>
          <span className="epi epi--stub">
            <span className="epi__d" />
            {t("statusPill")}
          </span>
        </div>
        <p className="d-hero__summary">
          {m.summary ? `${m.summary} ` : ""}
          {t("summaryTail")}
        </p>
        <dl className="d-hero__facts">
          {facts.map((f) => (
            <div key={f.key}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
        <div className="d-hero__notice" role="note">
          <span aria-hidden="true">ℹ️</span>
          <p>
            <b>{t("noticeTitle")}</b> {t("noticeBody")}
            <em>{t("noticeDraftEm")}</em>
            {t("noticeTail")}
          </p>
        </div>
      </div>

      {/* WHAT WILL APPEAR — section skeletons */}
      <Section
        title={t("skelSectionTitle")}
        sub={<span className="stub-lead">{t("skelSectionSub")}</span>}
      >
        <div className="skel-grid">
          {skelCards.map((card) => (
            <div
              key={card.key}
              className={`skelcard${card.wide ? " skelcard--wide" : ""}`}
            >
              <div className="skelcard__head">
                <span className="skelcard__ic" aria-hidden="true">
                  {card.icon}
                </span>
                <span className="skelcard__name">{card.name}</span>
                <span className="skelcard__badge">{card.badge}</span>
              </div>
              {card.sub ? <div className="skelcard__sub">{card.sub}</div> : null}
              <div className="skel-lines" aria-hidden="true">
                {card.lines.map((w, i) => (
                  <span key={`${card.key}-${i}`} className={`skel-line ${w}`} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* EXTERNAL SOURCES — real content before AI runs */}
      <Section title={t("extSectionTitle")} sub={t("extSectionSub")} divider>
        <div className="extsrc">
          {extCards.map((card) => (
            <a key={card.key} href={card.href} target="_blank" rel="noopener">
              <span className="extsrc__src">{card.src}</span>
              <span className="extsrc__title">{card.title}</span>
              <span className="extsrc__id">{card.id}</span>
            </a>
          ))}
        </div>
      </Section>

      {/* Sticky CTA — one conversion action */}
      <div className="stub-cta">
        {error ? (
          <p className="research__error stub-cta__error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="stub-cta__inner">
          <label className="stub-cta__consent">
            <input
              type="checkbox"
              checked={consent}
              disabled={activeRun != null}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              {t("consentPrefix")} <b>{t("consentBold")}</b> {t("consentSuffix")}
            </span>
          </label>
          <div className="stub-cta__act">
            {activeRun ? (
              <span className="stub-cta__running">{t("runningNote")}</span>
            ) : (
              <span className="stub-cta__eta">{t("ctaEta")}</span>
            )}
            <Button
              variant="primary"
              size="lg"
              type="button"
              onClick={onCtaClick}
              disabled={ctaDisabled}
            >
              {ctaLabel}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
