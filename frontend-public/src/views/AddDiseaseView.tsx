import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import { bootstrapDisease } from "../api/bootstrapDisease";
import { lookupDiseaseMetadata, type LookupDiseaseMetadataResponse } from "../api/lookupDisease";
import { repositories } from "../repositories";
import type { Disease } from "../types";
import "../styles/research.css";

const SLUG_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;

function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

type StepStatus = "idle" | "running" | "done" | "error";

interface Step {
  key: "lookup" | "bootstrap";
  status: StepStatus;
  label: string;
  detail?: string;
}

export interface AddDiseaseViewProps {
  readonly onNav: (path: string) => void;
}

export function AddDiseaseView({ onNav }: AddDiseaseViewProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [matches, setMatches] = useState<readonly Disease[]>([]);
  const [steps, setSteps] = useState<Step[]>([
    { key: "lookup", status: "idle", label: "Search disease databases" },
    { key: "bootstrap", status: "idle", label: "Start research workflows" },
  ]);
  const [metadata, setMetadata] = useState<LookupDiseaseMetadataResponse | null>(null);

  const displayMatches = useMemo(
    () => (name.trim().length < 2 ? [] : matches),
    [matches, name],
  );

  const exactDuplicate = useMemo(
    () =>
      displayMatches.find(
        (d) => d.name.toLowerCase() === name.trim().toLowerCase(),
      ),
    [displayMatches, name],
  );

  useEffect(() => {
    const q = name.trim();
    let cancelled = false;
    if (q.length < 2) {
      return;
    }
    const t = window.setTimeout(async () => {
      try {
        const repo = repositories().diseases;
        const hits = await repo.searchDiseases(q);
        if (!cancelled) {
          setMatches(hits.slice(0, 4));
        }
      } catch {
        if (!cancelled) {
          setMatches([]);
        }
      }
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [name]);

  const updateStep = useCallback(
    (key: Step["key"], patch: Partial<Step>) => {
      setSteps((prev) =>
        prev.map((s) => (s.key === key ? { ...s, ...patch } : s)),
      );
    },
    [],
  );

  const canSubmit =
    !busy && name.trim().length >= 2 && !exactDuplicate;

  const progressPct = useMemo(() => {
    const lookup = steps.find((s) => s.key === "lookup");
    const bootstrap = steps.find((s) => s.key === "bootstrap");
    if (bootstrap?.status === "done") return 100;
    if (bootstrap?.status === "running") return 75;
    if (lookup?.status === "done") return 50;
    if (lookup?.status === "running") return 25;
    return 0;
  }, [steps]);

  const start = useCallback(async () => {
    setError(null);
    setMetadata(null);
    if (!canSubmit) return;
    setBusy(true);
    setSteps([
      { key: "lookup", status: "running", label: "Searching disease databases…" },
      { key: "bootstrap", status: "idle", label: "Start research workflows" },
    ]);

    let resolved: LookupDiseaseMetadataResponse;
    try {
      resolved = await lookupDiseaseMetadata({ name: name.trim() });
      setMetadata(resolved);
      const fields: string[] = [];
      if (resolved.omim) fields.push(`OMIM ${resolved.omim}`);
      if (resolved.gene) fields.push(resolved.gene);
      if (resolved.inheritance) fields.push(resolved.inheritance);
      const lookupDetail =
        resolved.model_used === "unavailable"
          ? `${resolved.canonical_name} (AI lookup unavailable — using your typed name)`
          : `${resolved.canonical_name}${
              fields.length ? "  ·  " + fields.join("  ·  ") : ""
            }`;
      updateStep("lookup", {
        status: "done",
        label: resolved.model_used === "unavailable" ? "Name accepted" : "Match found",
        detail: lookupDetail,
      });
    } catch (e) {
      const msg =
        e instanceof ApiRequestError && e.status === 401
          ? "Server rejected (401). API key gate is on."
          : e instanceof Error
            ? e.message
            : "Lookup failed.";
      updateStep("lookup", { status: "error", detail: msg });
      setError(msg);
      setBusy(false);
      return;
    }

    const canonical = resolved.canonical_name || name.trim();
    const slug = slugify(canonical);
    const existing = await repositories().diseases.getDiseaseBySlug(slug);
    if (existing) {
      const msg = `"${existing.name}" is already in the catalog.`;
      updateStep("bootstrap", { status: "error", detail: msg });
      setError(msg);
      setBusy(false);
      return;
    }
    if (!slug || !SLUG_PATTERN.test(slug)) {
      const msg = `Could not derive a URL-safe slug from "${canonical}".`;
      updateStep("bootstrap", { status: "error", detail: msg });
      setError(msg);
      setBusy(false);
      return;
    }

    updateStep("bootstrap", {
      status: "running",
      label: "Starting 6 research workflows…",
    });
    try {
      const res = await bootstrapDisease({
        slug,
        name: canonical,
        gene: resolved.gene,
        omim: resolved.omim,
        inheritance: resolved.inheritance,
        summary: resolved.summary,
      });
      updateStep("bootstrap", {
        status: "done",
        detail: "All 6 workflows running — redirecting to disease page…",
      });
      window.setTimeout(() => {
        onNav(`/diseases/${encodeURIComponent(res.disease_slug)}`);
      }, 700);
    } catch (e) {
      const msg =
        e instanceof ApiRequestError && e.status === 401
          ? "Server rejected (401). API key gate is on."
          : e instanceof Error
            ? e.message
            : "Bootstrap failed.";
      updateStep("bootstrap", { status: "error", detail: msg });
      setError(msg);
      setBusy(false);
    }
  }, [canSubmit, name, onNav, updateStep]);

  return (
    <section className="page page--research">
      <h1>Add a disease</h1>
      <p className="research__lead">
        Enter one thing you know — disease name, gene symbol, or OMIM number.
        The AI resolves the official disease record (canonical name, OMIM, gene,
        inheritance) and then fans out six research workflows in parallel.
      </p>

      {error != null ? (
        <p className="research__error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="research__field">
        <label htmlFor="add-query">Disease name, gene, or OMIM *</label>
        <input
          id="add-query"
          className="research__input"
          type="text"
          value={name}
          maxLength={200}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Marfan, FBN1, 154700, PKU"
          autoComplete="off"
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canSubmit) void start();
          }}
        />
        {exactDuplicate ? (
          <small className="research__error" role="alert">
            <strong>Already in catalog:</strong>{" "}
            <a
              href={`#/diseases/${encodeURIComponent(exactDuplicate.slug)}`}
              onClick={(e) => {
                e.preventDefault();
                onNav(`/diseases/${encodeURIComponent(exactDuplicate.slug)}`);
              }}
            >
              {exactDuplicate.name}
            </a>{" "}
            — open that page instead of creating a duplicate.
          </small>
        ) : displayMatches.length > 0 ? (
          <small className="research__hint" style={{ display: "block", marginTop: "0.35rem" }}>
            Similar in catalog:{" "}
            {displayMatches.map((d, i) => (
              <span key={d.slug}>
                {i > 0 ? ", " : ""}
                <a
                  href={`#/diseases/${encodeURIComponent(d.slug)}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNav(`/diseases/${encodeURIComponent(d.slug)}`);
                  }}
                >
                  {d.name}
                </a>
              </span>
            ))}
            . If your input is one of these, click it instead of bootstrapping a new entry.
          </small>
        ) : null}
      </div>

      <div className="research__actions">
        <Button
          variant="primary"
          type="button"
          disabled={!canSubmit}
          onClick={() => void start()}
        >
          {busy ? "Working…" : "Search & start research"}
        </Button>
        <Button type="button" disabled={busy} onClick={() => onNav("/diseases")}>
          Cancel
        </Button>
      </div>

      {busy || steps.some((s) => s.status !== "idle") ? (
        <div
          className="research__progress"
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="research__progress-bar"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      ) : null}

      {busy || steps.some((s) => s.status !== "idle") ? (
        <ol className="research__steps" aria-live="polite">
          {steps.map((s) => (
            <li key={s.key} className={`research__step research__step--${s.status}`}>
              <span className="research__step-icon" aria-hidden="true">
                {s.status === "running"
                  ? "⏳"
                  : s.status === "done"
                    ? "✓"
                    : s.status === "error"
                      ? "✕"
                      : "○"}
              </span>
              <span className="research__step-label">{s.label}</span>
              {s.detail ? (
                <span className="research__step-detail">{s.detail}</span>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {metadata?.summary && steps[0].status === "done" ? (
        <blockquote className="research__summary">
          {metadata.summary}
        </blockquote>
      ) : null}
    </section>
  );
}
