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
import {
  mergeAliasesRaw,
  parseAliasesRaw,
  suggestDiseaseAliases,
} from "../api/researchAliases";
import { getDataSource } from "../config/dataSource";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import "../styles/research.css";

const API_KEY_HINT =
  "If the backend has GENEGUIDELINES_API_KEY set, add the same value to VITE_GENEGUIDELINES_API_KEY locally (never in production public builds) or run guideline jobs from the operator console.";

type ResearchMode = "catalog" | "custom";

export interface StartResearchViewProps {
  readonly initialDiseaseSlug?: string;
  readonly onNav: (path: string) => void;
}

export function StartResearchView({
  initialDiseaseSlug,
  onNav,
}: StartResearchViewProps) {
  const { diseases, loading, error: catalogError } = useDiseaseCatalog("");
  const [mode, setMode] = useState<ResearchMode>(
    initialDiseaseSlug ? "catalog" : "custom",
  );
  const [slug, setSlug] = useState(initialDiseaseSlug ?? "");
  const [customName, setCustomName] = useState("");
  const [aliasesRaw, setAliasesRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [aliasBusy, setAliasBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSuggestAliases = useCallback(async () => {
    const name = customName.trim();
    if (!name) {
      setError("Enter a disease name before generating aliases.");
      return;
    }
    setAliasBusy(true);
    setError(null);
    try {
      const { aliases } = await suggestDiseaseAliases(name);
      setAliasesRaw((prev) => mergeAliasesRaw(prev, aliases));
    } catch (e) {
      if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Could not generate aliases.");
      }
    } finally {
      setAliasBusy(false);
    }
  }, [customName]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "catalog") {
        const diseaseSlug = slug.trim();
        if (!diseaseSlug) {
          setError("Choose a disease from the catalog list.");
          setBusy(false);
          return;
        }
        const { execution_id } = await startGuidelineRunPublic({
          mode: "catalog",
          diseaseSlug,
        });
        const q = `?disease=${encodeURIComponent(diseaseSlug)}`;
        onNav(`/research/${encodeURIComponent(execution_id)}${q}`);
        return;
      }

      const diseaseName = customName.trim();
      if (!diseaseName) {
        setError("Enter the disease name you want to research.");
        setBusy(false);
        return;
      }
      const { execution_id } = await startGuidelineRunPublic({
        mode: "custom",
        diseaseName,
        diseaseAliases: parseAliasesRaw(aliasesRaw),
      });
      const q = `?name=${encodeURIComponent(diseaseName)}`;
      onNav(`/research/${encodeURIComponent(execution_id)}${q}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setError(`The server rejected the request (401). ${API_KEY_HINT}`);
      } else if (e instanceof ApiRequestError && e.status === 429) {
        setError(e.message);
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Could not start the research run.");
      }
    } finally {
      setBusy(false);
    }
  }, [aliasesRaw, customName, mode, onNav, slug]);

  const dataSource = getDataSource();
  const apiBase = getApiBaseUrl();
  const hasDevKey = getOptionalApiKey() != null;
  const canStart =
    mode === "catalog"
      ? !loading && diseases.length > 0 && slug.trim().length > 0
      : customName.trim().length > 0;

  return (
    <section className="page page--research">
      <h1>Start research</h1>
      <p className="research__lead">
        Launches the PubMed guideline pipeline for a rare disease. Pick from the
        catalog or enter any disease name, optionally with AI-suggested search
        aliases — progress appears on the next screen.
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

      <fieldset className="research__mode">
        <legend className="research__mode-legend">Disease source</legend>
        <label className="research__mode-option">
          <input
            type="radio"
            name="research-mode"
            value="custom"
            checked={mode === "custom"}
            onChange={() => setMode("custom")}
          />
          Custom disease name
        </label>
        <label className="research__mode-option">
          <input
            type="radio"
            name="research-mode"
            value="catalog"
            checked={mode === "catalog"}
            onChange={() => setMode("catalog")}
          />
          From catalog
        </label>
      </fieldset>

      {mode === "catalog" ? (
        <div className="research__field">
          <label htmlFor="research-disease">Catalog disease</label>
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
      ) : (
        <>
          <div className="research__field">
            <label htmlFor="research-custom-name">Disease name</label>
            <input
              id="research-custom-name"
              className="research__input"
              type="text"
              value={customName}
              placeholder="e.g. fibrous dysplasia / McCune-Albright syndrome"
              onChange={(e) => setCustomName(e.target.value)}
            />
          </div>
          <div className="research__field">
            <label htmlFor="research-aliases">
              Search aliases (comma or newline)
            </label>
            <textarea
              id="research-aliases"
              className="research__textarea"
              rows={3}
              value={aliasesRaw}
              placeholder="FD/MAS, McCune-Albright, …"
              onChange={(e) => setAliasesRaw(e.target.value)}
            />
            <div className="research__alias-row">
              <Button
                type="button"
                disabled={aliasBusy || busy || !customName.trim()}
                onClick={() => void handleSuggestAliases()}
              >
                {aliasBusy ? "Generating aliases…" : "Generate aliases (AI)"}
              </Button>
              <span className="research__hint">
                Uses the same LLM endpoint as Doctor Finder — requires a
                configured API key on the backend.
              </span>
            </div>
          </div>
        </>
      )}

      <p className="research__hint">
        Model profile:{" "}
        <code>
          {DEFAULT_GUIDELINE_PROFILE ?? "server default (MODEL_PROFILE in .env)"}
        </code>
        . {API_KEY_HINT}{" "}
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
          disabled={busy || aliasBusy || !canStart}
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
