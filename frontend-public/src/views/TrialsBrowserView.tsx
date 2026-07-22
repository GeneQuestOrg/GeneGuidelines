import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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

const PHASE_FILTER_ALL = "all";

type ViewMode = "both" | "list" | "map";

export function TrialsBrowserView({ userLoc, search, onNav }: TrialsBrowserViewProps) {
  const { t } = useTranslation("trials");
  const { trials, loading, error } = useTrials();
  const { diseases, loading: diseasesLoading } = useDiseaseCatalog();
  const [viewMode, setViewMode] = useState<ViewMode>("both");

  const STATUS_FILTERS: readonly { value: TrialStatusFilter; label: string }[] = [
    { value: "recruiting", label: t("statusOptionRecruiting") },
    { value: "active_not_recruiting", label: t("statusOptionActiveNotRecruiting") },
    { value: "completed", label: t("statusOptionCompleted") },
    { value: STATUS_FILTER_ALL, label: t("statusOptionAny") },
  ];

  const PHASE_FILTERS: readonly { value: string; label: string }[] = [
    { value: PHASE_FILTER_ALL, label: t("phaseOptionAny") },
    { value: "1", label: t("phaseOption1") },
    { value: "2", label: t("phaseOption2") },
    { value: "3", label: t("phaseOption3") },
    { value: "4", label: t("phaseOption4") },
  ];

  const SORT_OPTIONS: readonly { value: string; label: string }[] = [
    { value: "status", label: t("sortOptionStatus") },
    { value: "nearest", label: t("sortOptionNearest") },
    { value: "date", label: t("sortOptionDate") },
  ];
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
          <h1 className="page__title">{t("title")}</h1>
          <div className="view-toggle" role="group" aria-label={t("switchView")}>
            <button
              className={`view-toggle__btn${viewMode === "list" ? " is-active" : ""}`}
              onClick={() => setViewMode("list")}
              title={t("viewListOnly")}
              aria-pressed={viewMode === "list"}
            >
              ☰
            </button>
            <button
              className={`view-toggle__btn${viewMode === "both" ? " is-active" : ""}`}
              onClick={() => setViewMode("both")}
              title={t("viewListAndMap")}
              aria-pressed={viewMode === "both"}
            >
              ⊞
            </button>
            <button
              className={`view-toggle__btn${viewMode === "map" ? " is-active" : ""}`}
              onClick={() => setViewMode("map")}
              title={t("viewMapOnly")}
              aria-pressed={viewMode === "map"}
            >
              ⊕
            </button>
          </div>
        </div>
        <p className="page__lead">{t("lead")}</p>
      </header>

      <div className="dfilters">
        {activeDiseaseSlug != null ? (
          <div className="dchip">
            <span className="dchip__label">{activeDiseaseLabel}</span>
            <button
              type="button"
              className="dchip__x"
              onClick={handleClearDisease}
              aria-label={t("clearDiseaseFilter")}
            >
              ×
            </button>
          </div>
        ) : (
          <div className="dfilters__search">
            <DiseaseAutocomplete
              placeholder={t("diseaseSearchPlaceholder")}
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
            label={t("filterStatusLabel")}
            value={query.status}
            neutralValue="recruiting"
            options={STATUS_FILTERS}
            onPick={(v) => patchQuery({ status: v as TrialStatusFilter })}
          />
          <FilterMenu
            label={t("filterPhaseLabel")}
            value={query.phase ?? PHASE_FILTER_ALL}
            options={PHASE_FILTERS}
            onPick={(v) =>
              patchQuery({ phase: v === PHASE_FILTER_ALL ? null : (v as TrialPhase) })
            }
          />
          <FilterMenu
            label={t("filterSortLabel")}
            value={query.sort}
            neutralValue="status"
            options={SORT_OPTIONS}
            onPick={(v) => patchQuery({ sort: v as TrialsQuery["sort"] })}
          />
        </div>
      </div>

      {diseasesLoading ? <p className="page__loading">{t("loadingDiseaseCatalog")}</p> : null}
      {loading ? <p className="page__loading">{t("loadingTrials")}</p> : null}
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
                  {t("resultCount", {
                    count: items.length,
                    range:
                      pageCount > 1
                        ? t("showingRange", {
                            start: pageStart + 1,
                            end: pageStart + visibleItems.length,
                          })
                        : "",
                  })}
                </p>
              ) : null}
              {items.length > 0 ? <TrialsList trials={visibleItems} /> : null}
              {items.length === 0 ? (
                unknownDisease != null ? (
                  <p className="d-panel-empty">
                    {t("emptyUnknownDiseasePrefix")} <strong>{unknownDisease}</strong>
                    {t("emptyUnknownDiseaseYet")} <button
                      type="button"
                      className="link-btn"
                      onClick={() => onNav("/start-research")}
                    >
                      {t("startResearchRun")}
                    </button>
                    {t("emptyUnknownDiseaseSuffix")}
                  </p>
                ) : (
                  <p className="d-panel-empty">{t("emptyNoMatches")}</p>
                )
              ) : null}
              <Pagination
                page={safePage}
                pageCount={pageCount}
                onPage={(p) => patchQuery({ page: p })}
              />
              {items.length > 0 ? (
                <p className="doctors-provenance">{t("provenance")}</p>
              ) : null}
            </div>
          ) : null}
          {viewMode !== "list" ? <TrialsMap trials={items} userLoc={effectiveUserLoc} /> : null}
        </div>
      ) : null}
    </section>
  );
}
