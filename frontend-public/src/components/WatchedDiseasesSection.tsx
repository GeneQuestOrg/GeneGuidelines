import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  fetchWatches,
  unwatchDisease,
  watchDisease,
  type WatchedDisease,
} from "../api/account";
import { repositories } from "../repositories";
import type { Disease } from "../types";

interface WatchedDiseasesSectionProps {
  onNav: (path: string) => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function StatusBadge({ status }: { status: string | null }) {
  if (status == null) return null;
  let cls = "account__status-badge";
  if (status === "published") cls += " account__status-badge--completed";
  else if (status === "ai-draft") cls += " account__status-badge--running";
  else cls += " account__status-badge--failed";
  return <span className={cls}>{status}</span>;
}

export function WatchedDiseasesSection({ onNav }: WatchedDiseasesSectionProps) {
  const [watches, setWatches] = useState<readonly WatchedDisease[] | null>(null);
  const [catalog, setCatalog] = useState<readonly Disease[] | null>(null);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);

  const reloadWatches = useCallback(() => {
    return fetchWatches()
      .then((data) => {
        setWatches(data);
        return data;
      })
      .catch(() => {
        setWatches([]);
        return [] as readonly WatchedDisease[];
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void reloadWatches();
    void repositories()
      .diseases.listDiseases()
      .then((diseases) => {
        if (!cancelled) setCatalog(diseases);
      })
      .catch(() => {
        if (!cancelled) setCatalog([]);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadWatches]);

  const watchedSlugs = useMemo(
    () => new Set((watches ?? []).map((w) => w.disease_slug)),
    [watches],
  );

  const addableDiseases = useMemo(() => {
    if (catalog == null) return [];
    return [...catalog]
      .filter((d) => !watchedSlugs.has(d.slug))
      .sort((a, b) => a.nameShort.localeCompare(b.nameShort));
  }, [catalog, watchedSlugs]);

  const unwatch = useCallback((slug: string) => {
    setWatches((prev) => (prev == null ? prev : prev.filter((w) => w.disease_slug !== slug)));
    unwatchDisease(slug).catch(() => {
      void reloadWatches();
    });
  }, [reloadWatches]);

  const addWatch = useCallback(async () => {
    const slug = selectedSlug.trim();
    if (slug === "" || isAdding) return;
    setAddError(null);
    setIsAdding(true);
    try {
      const added = await watchDisease(slug);
      setWatches((prev) => {
        const base = prev ?? [];
        if (base.some((w) => w.disease_slug === added.disease_slug)) return base;
        return [added, ...base];
      });
      setSelectedSlug("");
    } catch (e: unknown) {
      if (e instanceof Error) {
        setAddError(e.message);
      } else {
        setAddError("Could not add this disease. Try again.");
      }
      void reloadWatches();
    } finally {
      setIsAdding(false);
    }
  }, [isAdding, reloadWatches, selectedSlug]);

  return (
    <div className="account__watches">
      <h3 className="account__section-title">My diseases</h3>
      <p className="account__watches-lead">
        Follow diseases you care about. You can add them here or use Watch on any disease page.
      </p>

      <div className="account__watch-add">
        <label className="account__watch-add-label" htmlFor="account-watch-select">
          Add a disease
        </label>
        <div className="account__watch-add-row">
          <select
            id="account-watch-select"
            className="account__watch-select"
            value={selectedSlug}
            disabled={catalog == null || addableDiseases.length === 0 || isAdding}
            onChange={(e) => {
              setSelectedSlug(e.target.value);
              setAddError(null);
            }}
          >
            <option value="">
              {catalog == null
                ? "Loading catalog…"
                : addableDiseases.length === 0
                  ? "All catalog diseases are already followed"
                  : "Choose a disease…"}
            </option>
            {addableDiseases.map((d) => (
              <option key={d.slug} value={d.slug}>
                {d.nameShort} — {d.name}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="primary"
            disabled={selectedSlug === "" || isAdding}
            onClick={() => void addWatch()}
          >
            {isAdding ? "Adding…" : "Add"}
          </Button>
        </div>
        {addError != null ? (
          <p className="account__alert" role="alert">
            {addError}
          </p>
        ) : null}
        <p className="account__quota-hint">
          <button
            type="button"
            className="account__inline-link"
            onClick={() => onNav("/diseases")}
          >
            Browse all diseases
          </button>
          {" · "}
          <button
            type="button"
            className="account__inline-link"
            onClick={() => onNav("/add-disease")}
          >
            Add a new disease to the catalog
          </button>
        </p>
      </div>

      {watches == null ? (
        <p className="account__loading">Loading your list…</p>
      ) : watches.length === 0 ? (
        <p className="account__empty-runs">
          You are not following any diseases yet. Pick one above or open a disease page and tap
          Watch.
        </p>
      ) : (
        <ul className="account__watches-list">
          {watches.map((w) => (
            <li key={w.disease_slug} className="account__watch-item">
              {w.active_run_id != null ? (
                <span className="account__watch-pulse" aria-hidden />
              ) : null}
              <span className="account__watch-name">
                {w.name_short ?? w.disease_slug}
              </span>
              <StatusBadge status={w.disease_status} />
              <span className="account__watch-meta">
                {w.active_run_id != null ? "Research in progress · " : ""}
                {w.last_run_at != null ? `Last run ${formatDate(w.last_run_at)}` : ""}
              </span>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onNav(`/diseases/${w.disease_slug}`)}
              >
                Open
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => unwatch(w.disease_slug)}
              >
                Unwatch
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
