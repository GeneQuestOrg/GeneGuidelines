import { useCallback, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  ApiRequestError,
  getApiBaseUrl,
  getOptionalApiKey,
} from "../api/client";
import {
  DEFAULT_GUIDELINE_PROFILE,
  startGuidelineRunPublic,
} from "../api/guidelineRun";
import { getDataSource } from "../config/dataSource";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../styles/research.css";

const API_KEY_HINT =
  "If the backend has GENEGUIDELINES_API_KEY set, add the same value to VITE_GENEGUIDELINES_API_KEY locally (never in production public builds) or run guideline jobs from the operator console.";

export interface StartResearchViewProps {
  readonly initialDiseaseSlug?: string;
  readonly onNav: (path: string) => void;
}

export function StartResearchView({
  initialDiseaseSlug,
  onNav,
}: StartResearchViewProps) {
  const { diseases, loading, error: catalogError } = useDiseaseCatalog("");
  const [slug, setSlug] = useState(initialDiseaseSlug ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    const diseaseSlug = slug.trim();
    if (!diseaseSlug) {
      setError("Choose a disease from the list.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { execution_id } = await startGuidelineRunPublic(
        diseaseSlug,
        DEFAULT_GUIDELINE_PROFILE,
      );
      const q = `?disease=${encodeURIComponent(diseaseSlug)}`;
      onNav(`/research/${encodeURIComponent(execution_id)}${q}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setError(
          `The server rejected the request (401). ${API_KEY_HINT}`,
        );
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Could not start the research run.");
      }
    } finally {
      setBusy(false);
    }
  }, [onNav, slug]);

  const dataSource = getDataSource();
  const apiBase = getApiBaseUrl();
  const hasDevKey = getOptionalApiKey() != null;

  return (
    <section className="page page--research">
      <h1>Start research</h1>
      <p className="research__lead">
        Launches the PubMed guideline pipeline for a catalog disease. This is a
        long-running job on the server (model + tools) — progress appears on the
        next screen.
      </p>
      {dataSource === "fixture" ? (
        <p className="research__hint" role="status">
          Data layer is <code>fixture</code>. Start still calls the real backend
          at{" "}
          <code>{apiBase || "(same origin / Vite proxy)"}</code>
          — set <code>VITE_DATA_SOURCE=api</code> if you want catalog + pipeline
          aligned with SQLite.
        </p>
      ) : null}
      {catalogError != null ? (
        <p className="research__error" role="alert">
          {catalogError}
        </p>
      ) : null}
      {error != null ? (
        <p className="research__error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="research__field">
        <label htmlFor="research-disease">Disease</label>
        <select
          id="research-disease"
          className="research__select"
          value={slug}
          disabled={loading || diseases.length === 0}
          onChange={(e) => setSlug(e.target.value)}
        >
          <option value="">
            {loading ? "Loading catalog…" : "Select a disease…"}
          </option>
          {diseases.map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.nameShort} — {d.name}
            </option>
          ))}
        </select>
      </div>
      <p className="research__hint">
        Uses model profile <code>{DEFAULT_GUIDELINE_PROFILE}</code> (server{" "}
        <code>MODEL_PROFILES</code>). {API_KEY_HINT}{" "}
        {hasDevKey ? (
          <span>
            A dev key is <strong>present</strong> in this build.
          </span>
        ) : (
          <span>
            No <code>VITE_GENEGUIDELINES_API_KEY</code> in this bundle — OK when
            the server auth gate is off.
          </span>
        )}
      </p>
      <div className="research__actions">
        <Button
          variant="primary"
          type="button"
          disabled={busy || loading || diseases.length === 0}
          onClick={() => void start()}
        >
          {busy ? "Starting…" : "Start PubMed run"}
        </Button>
        <Button type="button" onClick={() => onNav("/")}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
