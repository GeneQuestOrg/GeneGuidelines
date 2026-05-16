import { useMemo, useState } from "react";
import type { UserLocation } from "../router/types";
import type { PubmedRole } from "../types/doctor";
import { DiseaseSelect } from "../components/DiseaseSelect";
import { DoctorCard } from "../components/DoctorCard";
import { DoctorsMap } from "../components/DoctorsMap";
import { FilterChips } from "../components/FilterChips";
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

  const items = useMemo(() => {
    if (!activeDiseaseSlug) {
      return [];
    }
    let rows = attachDoctorDistances(doctors, userLoc);
    rows = rows.filter((d) => d.diseases.includes(activeDiseaseSlug));
    if (roleFilter !== ROLE_FILTER_ALL) {
      rows = rows.filter((d) => d.pubmedRole === (roleFilter as PubmedRole));
    }
    return sortDoctorsByDistanceThenScore(rows);
  }, [doctors, userLoc, activeDiseaseSlug, roleFilter]);

  const catalogReady = !diseasesLoading && diseases.length > 0;

  return (
    <section className="page page--doctors">
      <header className="page__head">
        <h1 className="page__title">Find a specialist</h1>
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
        <div className="doctors-layout">
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
                No specialists in the directory for this disease yet. Try another role filter
                or check back after a Doctor Finder run.
              </p>
            ) : null}
          </div>
          <DoctorsMap doctors={items} userLoc={userLoc} onNav={onNav} />
        </div>
      ) : null}
    </section>
  );
}
