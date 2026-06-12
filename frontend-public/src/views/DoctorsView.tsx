import { useMemo, useState } from "react";
import type { UserLocation } from "../router/types";
import type { DiseaseSuggestion } from "../api/diseaseIndex";
import type { PubmedRole } from "../types/doctor";
import { DiseaseAutocomplete } from "../components/DiseaseAutocomplete";
import { DoctorCard } from "../components/DoctorCard";
import { DoctorsMap } from "../components/DoctorsMap";
import { FilterChips } from "../components/FilterChips";
import { LocationPicker } from "../components/LocationPicker";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useDoctors } from "../hooks/useDoctors";
import {
  attachDoctorDistances,
  sortDoctorsByDistanceThenScore,
} from "../utils/doctorSort";
import { filterDoctors, type SourceFilter } from "../utils/doctorFilters";
import { pubmedRoleLabel } from "../utils/doctorLabels";
import "../styles/doctors.css";

export interface DoctorsViewProps {
  readonly userLoc: UserLocation | null;
  readonly initialDisease?: string;
  readonly onNav: (path: string) => void;
}

const ROLE_FILTER_ALL = "all";

const ROLE_FILTERS: readonly { value: string; label: string }[] = [
  { value: ROLE_FILTER_ALL, label: "All roles" },
  { value: "research_leader", label: pubmedRoleLabel("research_leader") },
  { value: "research_participant", label: pubmedRoleLabel("research_participant") },
  { value: "case_study_author", label: pubmedRoleLabel("case_study_author") },
];

const SOURCE_FILTERS: readonly { value: SourceFilter; label: string }[] = [
  { value: "all", label: "All sources" },
  { value: "pubmed", label: "PubMed" },
  { value: "parent", label: "Parent-added" },
  { value: "consortium", label: "Consortium" },
];

type DistanceMax = 25 | 100 | 500 | null;

const DISTANCE_FILTERS: readonly { value: DistanceMax; label: string }[] = [
  { value: null, label: "Worldwide" },
  { value: 25, label: "25 km" },
  { value: 100, label: "100 km" },
  { value: 500, label: "500 km" },
];

type ViewMode = "both" | "list" | "map";

const PAGE_SIZE = 12;

export function DoctorsView({ userLoc, initialDisease, onNav }: DoctorsViewProps) {
  const { doctors, loading, error } = useDoctors();
  const { diseases, loading: diseasesLoading } = useDiseaseCatalog();
  const [roleFilter, setRoleFilter] = useState(ROLE_FILTER_ALL);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [parentOnly, setParentOnly] = useState(false);
  const [maxKm, setMaxKm] = useState<DistanceMax>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("both");
  const [localUserLoc, setLocalUserLoc] = useState<UserLocation | null>(null);
  const [localLocLabel, setLocalLocLabel] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  // Picking a non-catalog disease shows an empty state with a research CTA. The filter itself
  // is navigation-driven (?disease=…); this flag is local because such a slug has no list rows.
  const [unknownDisease, setUnknownDisease] = useState<string | null>(null);

  const effectiveUserLoc = localUserLoc ?? userLoc;

  // The active disease filter is driven by the route (initialDisease prop), not local state, so
  // deep-links and back-navigation stay the source of truth.
  const activeDiseaseSlug = initialDisease ?? null;

  const activeDiseaseLabel = useMemo(() => {
    if (!activeDiseaseSlug) {
      return null;
    }
    return diseases.find((d) => d.slug === activeDiseaseSlug)?.name ?? activeDiseaseSlug;
  }, [diseases, activeDiseaseSlug]);

  // Reset pagination whenever any filter changes. Done during render (React's documented pattern
  // for adjusting state in response to prop/state changes) so the eslint set-state-in-effect rule
  // stays satisfied and the slice never lags a frame behind the filters.
  const filterSignature = [
    activeDiseaseSlug ?? "",
    roleFilter,
    sourceFilter,
    String(parentOnly),
    String(maxKm),
    effectiveUserLoc ? `${effectiveUserLoc.lat},${effectiveUserLoc.lng}` : "",
  ].join("|");
  const [prevSignature, setPrevSignature] = useState(filterSignature);
  if (filterSignature !== prevSignature) {
    setPrevSignature(filterSignature);
    setVisibleCount(PAGE_SIZE);
  }

  const handlePickDisease = (suggestion: DiseaseSuggestion) => {
    if (suggestion.hasLocalRecord && suggestion.localSlug) {
      setUnknownDisease(null);
      onNav(`/doctors?disease=${encodeURIComponent(suggestion.localSlug)}`);
    } else {
      setUnknownDisease(suggestion.canonicalName);
    }
  };

  const handleClearDisease = () => {
    setUnknownDisease(null);
    onNav("/doctors");
  };

  const handleLocationChange = (loc: UserLocation | null, label: string | null) => {
    setLocalUserLoc(loc);
    setLocalLocLabel(label);
    if (loc === null) setMaxKm(null);
  };

  // Full filtered set — the map receives all of it; the list slices to visibleCount.
  const items = useMemo(() => {
    if (unknownDisease != null) {
      return [];
    }
    const rows = filterDoctors(attachDoctorDistances(doctors, effectiveUserLoc), {
      diseaseSlug: activeDiseaseSlug,
      role: roleFilter === ROLE_FILTER_ALL ? null : (roleFilter as PubmedRole),
      source: sourceFilter,
      parentOnly,
      maxKm,
    });
    return sortDoctorsByDistanceThenScore(rows);
  }, [
    doctors,
    effectiveUserLoc,
    activeDiseaseSlug,
    roleFilter,
    sourceFilter,
    parentOnly,
    maxKm,
    unknownDisease,
  ]);

  const visibleItems = useMemo(
    () => items.slice(0, visibleCount),
    [items, visibleCount],
  );

  const ready = !loading && error == null;

  return (
    <section className="page page--doctors">
      <header className="page__head">
        <div className="page__head-row">
          <h1 className="page__title">Find a specialist</h1>
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
          Factual signals, not our opinion. We don&rsquo;t divide doctors into trusted and the
          rest — we show what&rsquo;s documented: publications, guideline authorship, recent
          activity, and what other families report.
        </p>
      </header>

      <div className="filters">
        <div className="filters__field">
          <label htmlFor="doctors-disease-search">Filter by disease (optional)</label>
          <DiseaseAutocomplete
            placeholder="Type a disease name, gene, OMIM or Orphanet ID…"
            onPick={handlePickDisease}
            onMissingClick={() => onNav("/start-research")}
          />
        </div>
        {activeDiseaseSlug != null ? (
          <div className="filters__group">
            <span className="filters__label">Disease</span>
            <span className="active-disease-chip">
              {activeDiseaseLabel}
              <button
                type="button"
                className="active-disease-chip__clear"
                onClick={handleClearDisease}
                aria-label="Clear disease filter"
              >
                ×
              </button>
            </span>
          </div>
        ) : null}
        <div className="filters__group">
          <span className="filters__label">PubMed role</span>
          <FilterChips
            items={ROLE_FILTERS}
            active={roleFilter}
            onPick={setRoleFilter}
            ariaLabel="Filter by PubMed role"
          />
        </div>
        <div className="filters__group">
          <span className="filters__label">Source</span>
          <FilterChips
            items={SOURCE_FILTERS.map((f) => ({ value: f.value, label: f.label }))}
            active={sourceFilter}
            onPick={(v) => setSourceFilter(v as SourceFilter)}
            ariaLabel="Filter by data source"
          />
          <button
            type="button"
            className={`chip chip--btn doctors-toggle${parentOnly ? " is-active" : ""}`}
            aria-pressed={parentOnly}
            onClick={() => setParentOnly((v) => !v)}
          >
            Parent-recommended only
          </button>
        </div>
        <div className="filters__group filters__group--location">
          <span className="filters__label">Location</span>
          <LocationPicker
            value={localUserLoc}
            label={localLocLabel}
            onChange={handleLocationChange}
          />
        </div>
        {effectiveUserLoc != null ? (
          <div className="filters__group">
            <span className="filters__label">Distance</span>
            <FilterChips
              items={DISTANCE_FILTERS.map((f) => ({ value: String(f.value), label: f.label }))}
              active={String(maxKm)}
              onPick={(v) => setMaxKm(v === "null" ? null : (Number(v) as DistanceMax))}
              ariaLabel="Filter by distance"
            />
          </div>
        ) : null}
      </div>

      {diseasesLoading ? (
        <p className="page__loading">Loading disease catalog…</p>
      ) : null}
      {loading ? <p className="page__loading">Loading specialists…</p> : null}
      {error != null ? (
        <p className="d-panel-empty" role="alert">
          {error}
        </p>
      ) : null}

      {ready ? (
        <div className={`doctors-layout doctors-layout--${viewMode}`}>
          {viewMode !== "map" ? (
            <div className="doctors-list">
              {visibleItems.map((doctor) => (
                <DoctorCard
                  key={doctor.slug}
                  doctor={doctor}
                  km={doctor.km}
                  onNav={onNav}
                />
              ))}
              {items.length === 0 ? (
                unknownDisease != null ? (
                  <p className="d-panel-empty">
                    No specialists are listed for <strong>{unknownDisease}</strong> yet.{" "}
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
                    No specialists match the current filters. Try a different role, source, or
                    distance filter.
                  </p>
                )
              ) : null}
              {items.length > visibleItems.length ? (
                <button
                  type="button"
                  className="doctors-show-more"
                  onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                >
                  Show more ({items.length - visibleItems.length} more)
                </button>
              ) : null}
              {items.length > 0 ? (
                <p className="doctors-provenance">
                  Profiles are built from public sources (PubMed, clinic websites) and family
                  reports. A profile can be withdrawn at any time — write to{" "}
                  <a href="mailto:kontakt@genequest.org">kontakt@genequest.org</a>.
                </p>
              ) : null}
            </div>
          ) : null}
          {viewMode !== "list" ? (
            <DoctorsMap doctors={items} userLoc={effectiveUserLoc} onNav={onNav} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
