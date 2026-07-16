import { useCallback, useMemo, useState } from "react";
import type { UserLocation } from "../router/types";
import type { DiseaseSuggestion } from "../api/diseaseIndex";
import { attachTrialDistances } from "../api/trials";
import { DiseaseAutocomplete } from "../components/DiseaseAutocomplete";
import { FilterMenu } from "../components/FilterMenu";
import { LocationMenu, type DistanceMax } from "../components/LocationMenu";
import { Pagination } from "../components/Pagination";
import { TrialsList } from "../components/TrialsList";
import { TrialsMap } from "../components/TrialsMap";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useTrials } from "../hooks/useTrials";
import {
  PAGE_SIZE,
  filterTrials,
  parseTrialsQuery,
  queryRecordFromSearch,
  serializeTrialsQuery,
  sortTrials,
  type TrialsQuery,
  type TrialPhase,
  type TrialStatusFilter,
} from "../utils/trialsQuery";
import "../styles/doctors.css";

export interface TrialsBrowserViewProps {
  readonly userLoc: UserLocation | null;
  /** Current `location.search` — the single source of truth for every facet, sort, and page. */
  readonly search: string;
  readonly onNav: (path: string) => void;
}

const STATUS_FILTER_ALL = "all";

const STATUS_FILTERS: readonly { value: TrialStatusFilter; label: string }[] = [
  { value: "recruiting", label: "Recruiting" },
  { value: "active_not_recruiting", label: "Active, not recruiting" },
  { value: "completed", label: "Completed" },
  { value: STATUS_FILTER_ALL, label: "Any status" },
];

const PHASE_FILTER_ALL = "all";

const PHASE_FILTERS: readonly { value: string; label: string }[] = [
  { value: PHASE_FILTER_ALL, label: "Any phase" },
  { value: "1", label: "Phase 1" },
  { value: "2", label: "Phase 2" },
  { value: "3", label: "Phase 3" },
  { value: "4", label: "Phase 4" },
];

const SORT_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "status", label: "Status" },
  { value: "nearest", label: "Nearest" },
  { value: "date", label: "Most recent" },
];

type ViewMode = "both" | "list" | "map";

export function TrialsBrowserView({ userLoc, search, onNav }: TrialsBrowserViewProps) {
  const { trials, loading, error } = useTrials();
  const { diseases, loading: diseasesLoading } = useDiseaseCatalog();
  const [viewMode, setViewMode] = useState<ViewMode>("both");
  // Picking a non-catalog disease shows an empty state. Such a name has no slug
  // and no rows, so it is transient local state rather than part of the URL query.
  const [unknownDisease, setUnknownDisease] = useState<string | null>(null);

  // The full faceted state lives in the URL: one parsed query object is the single source of
  // truth, so deep-links, shares, and the browser back button all restore the exact view.
  const query = useMemo(() => parseTrialsQuery(queryRecordFromSearch(search)), [search]);

  const patchQuery = useCallback(
    (partial: Partial<TrialsQuery>) => {
      const merged: TrialsQuery = { ...query, ...partial };
      // Any facet/sort change returns to page 1; only an explicit page change keeps the page.
      const next = "page" in partial ? merged : { ...merged, page: 1 };
      onNav(serializeTrialsQuery(next));
    },
    [query, onNav],
  );

  const effectiveUserLoc = query.loc ?? userLoc;
  const activeDiseaseSlug = query.disease;

  const activeDiseaseLabel = useMemo(() => {
    if (!activeDiseaseSlug) {
      return null;
    }
    return diseases.find((d) => d.slug === activeDiseaseSlug)?.name ?? activeDiseaseSlug;
  }, [diseases, activeDiseaseSlug]);

  const handlePickDisease = (suggestion: DiseaseSuggestion) => {
    if (suggestion.hasLocalRecord && suggestion.localSlug) {
      setUnknownDisease(null);
      patchQuery({ disease: suggestion.localSlug });
    } else {
      setUnknownDisease(suggestion.canonicalName);
    }
  };

  const handleClearDisease = () => {
    setUnknownDisease(null);
    patchQuery({ disease: null });
  };

  const handleLocationChange = (loc: UserLocation | null, label: string | null) => {
    patchQuery({
      loc,
      locLabel: label,
      maxKm: loc == null ? null : query.maxKm,
    });
  };

  // Full filtered + sorted set — the map receives all of it; the list slices to one page.
  const items = useMemo(() => {
    if (unknownDisease != null) {
      return [];
    }
    const rows = filterTrials(attachTrialDistances(trials, effectiveUserLoc), {
      diseaseSlug: activeDiseaseSlug,
      status: query.status,
      phase: query.phase,
      maxKm: query.maxKm,
    });
    return sortTrials(rows, query.sort);
  }, [
    trials,
    effectiveUserLoc,
    activeDiseaseSlug,
    query.status,
    query.phase,
    query.maxKm,
    query.sort,
    unknownDisease,
  ]);

  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, query.page), pageCount);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const visibleItems = useMemo(
    () => items.slice(pageStart, pageStart + PAGE_SIZE),
    [items, pageStart],
  );

  const ready = !loading && error == null;

  return (
    <section className="page page--doctors">
      <header className="page__head">
        <div className="page__head-row">
          <h1 className="page__title">Clinical trials</h1>
          <div className="view-toggle" role="group" aria-label="Switch view">
            <button
              className={`view-toggle__btn${viewMode === "list" ? " is-active" : ""}`}
              onClick={() => setViewMode("list")}
              title="List only"
              aria-pressed={viewMode === "list"}
            >
              ☰
            </button>
            <button
              className={`view-toggle__btn${viewMode === "both" ? " is-active" : ""}`}
              onClick={() => setViewMode("both")}
              title="List and map"
              aria-pressed={viewMode === "both"}
            >
              ⊞
            </button>
            <button
              className={`view-toggle__btn${viewMode === "map" ? " is-active" : ""}`}
              onClick={() => setViewMode("map")}
              title="Map only"
              aria-pressed={viewMode === "map"}
            >
              ⊕
            </button>
          </div>
        </div>
        <p className="page__lead">
          Trials we have catalogued for these conditions, with their recruitment status and sites.
          GeneGuidelines does not run recruitment — every card links to the official
          ClinicalTrials.gov record for eligibility and contact details.
        </p>
      </header>

      <div className="dfilters">
        {activeDiseaseSlug != null ? (
          <div className="dchip">
            <span className="dchip__label">{activeDiseaseLabel}</span>
            <button
              type="button"
              className="dchip__x"
              onClick={handleClearDisease}
              aria-label="Clear disease filter"
            >
              ×
            </button>
          </div>
        ) : (
          <div className="dfilters__search">
            <DiseaseAutocomplete
              placeholder="Filter by disease — name, gene, OMIM…"
              onPick={handlePickDisease}
              onMissingClick={() => onNav("/start-research")}
            />
          </div>
        )}

        <div className="dfilters__menus">
          <LocationMenu
            value={query.loc}
            label={query.locLabel}
            maxKm={query.maxKm as DistanceMax}
            onChange={handleLocationChange}
            onPickRadius={(km) => patchQuery({ maxKm: km })}
          />
          <FilterMenu
            label="Status"
            value={query.status}
            neutralValue="recruiting"
            options={STATUS_FILTERS}
            onPick={(v) => patchQuery({ status: v as TrialStatusFilter })}
          />
          <FilterMenu
            label="Phase"
            value={query.phase ?? PHASE_FILTER_ALL}
            options={PHASE_FILTERS}
            onPick={(v) =>
              patchQuery({ phase: v === PHASE_FILTER_ALL ? null : (v as TrialPhase) })
            }
          />
          <FilterMenu
            label="Sort"
            value={query.sort}
            neutralValue="status"
            options={SORT_OPTIONS}
            onPick={(v) => patchQuery({ sort: v as TrialsQuery["sort"] })}
          />
        </div>
      </div>

      {diseasesLoading ? <p className="page__loading">Loading disease catalog…</p> : null}
      {loading ? <p className="page__loading">Loading trials…</p> : null}
      {error != null ? (
        <p className="d-panel-empty" role="alert">
          {error}
        </p>
      ) : null}

      {ready ? (
        <div className={`doctors-layout doctors-layout--${viewMode}`}>
          {viewMode !== "map" ? (
            <div className="doctors-list">
              {items.length > 0 ? (
                <p className="doctors-count">
                  {items.length} trial{items.length === 1 ? "" : "s"}
                  {pageCount > 1 ? (
                    <>
                      {" · showing "}
                      {pageStart + 1}–{pageStart + visibleItems.length}
                    </>
                  ) : null}
                </p>
              ) : null}
              {items.length > 0 ? <TrialsList trials={visibleItems} /> : null}
              {items.length === 0 ? (
                unknownDisease != null ? (
                  <p className="d-panel-empty">
                    No trials are catalogued for <strong>{unknownDisease}</strong> yet.{" "}
                    <button
                      type="button"
                      className="link-btn"
                      onClick={() => onNav("/start-research")}
                    >
                      Start a research run
                    </button>{" "}
                    to build the evidence base for this condition.
                  </p>
                ) : (
                  <p className="d-panel-empty">
                    No trials match the current filters. Try a different status, phase, or distance.
                  </p>
                )
              ) : null}
              <Pagination
                page={safePage}
                pageCount={pageCount}
                onPage={(p) => patchQuery({ page: p })}
              />
              {items.length > 0 ? (
                <p className="doctors-provenance">
                  Trial records are catalogued from ClinicalTrials.gov and may lag the registry.
                  Always confirm status, eligibility, and contact details on the official record.
                </p>
              ) : null}
            </div>
          ) : null}
          {viewMode !== "list" ? <TrialsMap trials={items} userLoc={effectiveUserLoc} /> : null}
        </div>
      ) : null}
    </section>
  );
}
