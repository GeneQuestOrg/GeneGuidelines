import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import { ApiRequestError } from "../api/client";
import { bootstrapDisease } from "../api/bootstrapDisease";
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

export interface AddDiseaseViewProps {
  readonly onNav: (path: string) => void;
}

export function AddDiseaseView({ onNav }: AddDiseaseViewProps) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [gene, setGene] = useState("");
  const [omim, setOmim] = useState("");
  const [inheritance, setInheritance] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [matches, setMatches] = useState<readonly Disease[]>([]);

  const derivedSlug = useMemo(() => (slugTouched ? slug : slugify(name)), [
    name,
    slug,
    slugTouched,
  ]);

  const exactDuplicate = useMemo(
    () =>
      matches.find(
        (d) =>
          d.slug === derivedSlug ||
          d.name.toLowerCase() === name.trim().toLowerCase(),
      ),
    [matches, derivedSlug, name],
  );

  useEffect(() => {
    const q = name.trim();
    let cancelled = false;
    if (q.length < 2) {
      const handle = window.setTimeout(() => {
        if (!cancelled) {
          setMatches([]);
        }
      }, 0);
      return () => {
        cancelled = true;
        window.clearTimeout(handle);
      };
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

  const slugInvalid = derivedSlug.length > 0 && !SLUG_PATTERN.test(derivedSlug);
  const canSubmit =
    !busy &&
    name.trim().length >= 2 &&
    derivedSlug.length >= 2 &&
    !slugInvalid &&
    !exactDuplicate;

  const start = useCallback(async () => {
    setError(null);
    if (!canSubmit) {
      return;
    }
    setBusy(true);
    try {
      const res = await bootstrapDisease({
        slug: derivedSlug,
        name: name.trim(),
        gene: gene.trim(),
        omim: omim.trim(),
        inheritance: inheritance.trim(),
        summary: summary.trim(),
      });
      onNav(`/diseases/${encodeURIComponent(res.disease_slug)}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        setError("Server rejected (401). API key gate is on — set VITE_GENEGUIDELINES_API_KEY locally or use the operator console.");
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Could not start the bootstrap.");
      }
    } finally {
      setBusy(false);
    }
  }, [canSubmit, derivedSlug, name, gene, omim, inheritance, summary, onNav]);

  return (
    <section className="page page--research">
      <h1>Add a disease</h1>
      <p className="research__lead">
        Creates a new catalog entry and fans out six AI workflows in parallel
        (official consensus paper, clinical trials, therapies, foundations,
        specialist directory, and the clinician living guideline). Live progress
        appears on the disease page.
      </p>

      {error != null ? (
        <p className="research__error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="research__field">
        <label htmlFor="add-name">Preferred name *</label>
        <input
          id="add-name"
          className="research__input"
          type="text"
          value={name}
          maxLength={200}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Alkaptonuria"
          autoComplete="off"
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
        ) : matches.length > 0 ? (
          <small className="research__hint" style={{ display: "block", marginTop: "0.35rem" }}>
            Similar in catalog:{" "}
            {matches.map((d, i) => (
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

      <div className="research__field">
        <label htmlFor="add-slug">URL slug</label>
        <input
          id="add-slug"
          className="research__input"
          type="text"
          value={derivedSlug}
          maxLength={64}
          onChange={(e) => {
            setSlug(e.target.value);
            setSlugTouched(true);
          }}
          placeholder="lowercase, dashes or underscores"
        />
        {slugInvalid ? (
          <small className="research__error">
            Slug must start with a letter or digit and use only lowercase letters,
            digits, dashes, or underscores.
          </small>
        ) : null}
      </div>

      <div className="research__field-row">
        <div className="research__field">
          <label htmlFor="add-gene">Gene</label>
          <input
            id="add-gene"
            className="research__input"
            type="text"
            value={gene}
            maxLength={80}
            onChange={(e) => setGene(e.target.value)}
            placeholder="e.g. HGD"
          />
        </div>
        <div className="research__field">
          <label htmlFor="add-omim">OMIM</label>
          <input
            id="add-omim"
            className="research__input"
            type="text"
            value={omim}
            maxLength={40}
            onChange={(e) => setOmim(e.target.value)}
            placeholder="e.g. 203500"
          />
        </div>
      </div>

      <div className="research__field">
        <label htmlFor="add-inheritance">Inheritance</label>
        <input
          id="add-inheritance"
          className="research__input"
          type="text"
          value={inheritance}
          maxLength={80}
          onChange={(e) => setInheritance(e.target.value)}
          placeholder="e.g. Autosomal recessive"
        />
      </div>

      <div className="research__field">
        <label htmlFor="add-summary">Clinical summary</label>
        <textarea
          id="add-summary"
          className="research__input"
          value={summary}
          rows={3}
          maxLength={2000}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="One-paragraph clinical description"
        />
      </div>

      <p className="research__hint">
        Six workflows will fan out in parallel. The four fast ones
        (official guidelines, trials, therapies, foundations) complete in
        roughly a minute; the doctor finder and living guideline pipelines
        run longer.
      </p>

      <div className="research__actions">
        <Button
          variant="primary"
          type="button"
          disabled={!canSubmit}
          onClick={() => void start()}
        >
          {busy ? "Bootstrapping…" : "Add disease & run research"}
        </Button>
        <Button type="button" onClick={() => onNav("/diseases")}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
