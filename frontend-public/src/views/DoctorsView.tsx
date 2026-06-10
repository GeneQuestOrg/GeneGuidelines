import { useMemo, useState } from "react";
import type { UserLocation } from "../router/types";
import type { PubmedRole } from "../types/doctor";
import { DiseaseSelect } from "../components/DiseaseSelect";
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

type DistanceMax = 25 | 100 | 500 | null;

const DISTANCE_FILTERS: readonly { value: DistanceMax; label: string }[] = [
  { value: null, label: "Worldwide" },
  { value: 25, label: "25 km" },
  { value: 100, label: "100 km" },
  { value: 500, label: "500 km" },
];

type ViewMode = "both" | "list" | "map";

function resolveDiseaseSlug(
  diseases: readonly { slug: string }[],
  preferred: string | undefined,
): string {
  if (diseases.length === 0) {
    return "";
  }
  if (preferred && diseases.some((d) => d.slug === preferred)) {
    return preferred;
  }
  return diseases[0].slug;
}

export function DoctorsView({ userLoc, initialDisease, onNav }: DoctorsViewProps) {
  const { doctors, loading, error } = useDoctors();
  const { diseases, loading: diseasesLoading } = useDiseaseCatalog();
  const [roleFilter, setRoleFilter] = useState(ROLE_FILTER_ALL);
  const [maxKm, setMaxKm] = useState<DistanceMax>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("both");
  const [localUserLoc, setLocalUserLoc] = useState<UserLocation | null>(null);
  const [localLocLabel, setLocalLocLabel] = useState<string | null>(null);

  const effectiveUserLoc = localUserLoc ?? userLoc;

  const activeDiseaseSlug = useMemo(
    () => resolveDiseaseSlug(diseases, initialDisease),
    [diseases, initialDisease],
  );

  const selectedDisease = useMemo(
    () => diseases.find((d) => d.slug === activeDiseaseSlug) ?? null,
    [diseases, activeDiseaseSlug],
  );

  const handleDiseaseChange = (slug: string) => {
    onNav(`/doctors?disease=${encodeURIComponent(slug)}`);
  };

  const handleLocationChange = (loc: UserLocation | null, label: string | null) => {
    setLocalUserLoc(loc);
    setLocalLocLabel(label);
    if (loc === null) setMaxKm(null);
  };

  const items = useMemo(() => {
    if (!activeDiseaseSlug) {
      return [];
    }
    let rows = attachDoctorDistances(doctors, effectiveUserLoc);
    rows = rows.filter((d) => d.diseases.includes(activeDiseaseSlug));
    if (roleFilter !== ROLE_FILTER_ALL) {
      rows = rows.filter((d) => d.pubmedRole === (roleFilter as PubmedRole));
    }
    if (maxKm != null && effectiveUserLoc != null) {
      rows = rows.filter((d) => d.km != null && d.km <= maxKm);
    }
    return sortDoctorsByDistanceThenScore(rows);
  }, [doctors, effectiveUserLoc, activeDiseaseSlug, roleFilter, maxKm]);

  const catalogReady = !diseasesLoading && diseases.length > 0;

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
          Choose your condition to see clinicians with PubMed-documented expertise. Ranking
          weighs first/last authorship, guideline citations, and recent activity.
        </p>
      </header>

      <div className="filters">
        <DiseaseSelect
          diseases={diseases}
          value={activeDiseaseSlug}
          onChange={handleDiseaseChange}
        />
        <div className="filters__group">
          <span className="filters__label">PubMed role</span>
          <FilterChips
            items={ROLE_FILTERS}
            active={roleFilter}
            onPick={setRoleFilter}
            ariaLabel="Filter by PubMed role"
          />
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

      {selectedDisease != null ? (
        <p className="doctors-disease-hint">
          Showing specialists for <strong>{selectedDisease.name}</strong>
        </p>
      ) : null}

      {diseasesLoading ? (
        <p className="page__loading">Loading disease catalog…</p>
      ) : null}
      {loading ? <p className="page__loading">Loading specialists…</p> : null}
      {error != null ? (
        <p className="d-panel-empty" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && error == null && catalogReady && activeDiseaseSlug ? (
        <div className={`doctors-layout doctors-layout--${viewMode}`}>
          {viewMode !== "map" ? (
            <div className="doctors-list">
              {items.map((doctor) => (
                <DoctorCard
                  key={doctor.slug}
                  doctor={doctor}
                  km={doctor.km}
                  onNav={onNav}
                />
              ))}
              {items.length === 0 ? (
                <p className="d-panel-empty">
                  No specialists match the current filters. Try a different role or distance
                  filter, or check back after a Doctor Finder run.
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
