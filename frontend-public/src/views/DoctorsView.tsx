import { useCallback, useMemo, useState } from "react";
import { Button } from "@gene-guidelines/ui";
import type { UserLocation } from "../router/types";
import type { DiseaseSuggestion } from "../api/diseaseIndex";
import type { PubmedRole } from "../types/doctor";
import { useAccountContext } from "../auth/accountContext";
import { addDoctorCtaMode } from "../utils/contributionGating";
import { AddDoctorModal } from "../components/AddDoctorModal";
import { DiseaseAutocomplete } from "../components/DiseaseAutocomplete";
import { DoctorCard } from "../components/DoctorCard";
import { DoctorsMap } from "../components/DoctorsMap";
import { FilterMenu } from "../components/FilterMenu";
import { LocationMenu, type DistanceMax } from "../components/LocationMenu";
import { Pagination } from "../components/Pagination";
import { useDiseaseCatalog } from "../hooks/useDiseaseCatalog";
import { useDoctors } from "../hooks/useDoctors";
import { attachDoctorDistances } from "../utils/doctorSort";
import { filterDoctors, hasParentSignal, type SourceFilter } from "../utils/doctorFilters";
import {
  DOCTOR_PRESETS,
  PAGE_SIZE,
  parseDoctorsQuery,
  queryRecordFromHash,
  serializeDoctorsQuery,
  sortDoctors,
  type DoctorsQuery,
} from "../utils/doctorsQuery";
import {
  pubmedRoleLabel,
  specialtyGroupsOf,
  workTypeLabel,
  WORK_TYPE_ORDER,
  type WorkType,
} from "../utils/doctorLabels";
import "../styles/doctors.css";

export interface DoctorsViewProps {
  readonly userLoc: UserLocation | null;
  /** Current window hash — the single source of truth for every facet, sort, and page. */
  readonly hash: string;
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

const SORT_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "best", label: "Best match" },
  { value: "distance", label: "Nearest" },
  { value: "recency", label: "Most recent" },
  { value: "score", label: "PubMed score" },
  { value: "name", label: "Name (A–Z)" },
];

const RECENCY_FILTER_ALL = "all";

const RECENCY_FILTERS: readonly { value: string; label: string }[] = [
  { value: RECENCY_FILTER_ALL, label: "Any time" },
  { value: "active_2y", label: "On top of it (≤2y)" },
  { value: "active_5y", label: "Recent (≤5y)" },
];

type ViewMode = "both" | "list" | "map";

export function DoctorsView({ hash, onNav }: DoctorsViewProps) {
  const { doctors, loading, error } = useDoctors();
  const { diseases, loading: diseasesLoading } = useDiseaseCatalog();
  const account = useAccountContext();
  const [addDoctorOpen, setAddDoctorOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("both");
  // Picking a non-catalog disease shows an empty state with a research CTA. Such a name has no
  // slug and no list rows, so it is transient local state rather than part of the URL query.
  const [unknownDisease, setUnknownDisease] = useState<string | null>(null);

  // The full faceted state lives in the URL: one parsed query object is the single source of
  // truth, so deep-links, shares, and the browser back button all restore the exact view.
  const query = useMemo(
    () => parseDoctorsQuery(queryRecordFromHash(hash)),
    [hash],
  );

  const patchQuery = useCallback(
    (partial: Partial<DoctorsQuery>) => {
      const merged: DoctorsQuery = { ...query, ...partial };
      // Any facet/sort change returns to page 1; only an explicit page change keeps the page.
      const next = "page" in partial ? merged : { ...merged, page: 1 };
      onNav(serializeDoctorsQuery(next));
    },
    [query, onNav],
  );

  const toggleWorkType = useCallback(
    (w: WorkType) => {
      const has = query.workTypes.includes(w);
      const workTypes = has
        ? query.workTypes.filter((x) => x !== w)
        : [...query.workTypes, w];
      patchQuery({ workTypes });
    },
    [query.workTypes, patchQuery],
  );

  // Location is opt-in. Only a place the visitor explicitly chooses (query.loc) drives distance
  // sorting/filtering; the ambient default-city location must never silently reorder the global
  // ranking, otherwise a nearby low-relevance doctor outranks a world expert by accident.
  const effectiveUserLoc = query.loc;
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
    const rows = filterDoctors(attachDoctorDistances(doctors, effectiveUserLoc), {
      diseaseSlug: activeDiseaseSlug,
      role: query.role,
      source: query.source,
      parentOnly: query.parentOnly,
      maxKm: query.maxKm,
      workTypes: query.workTypes,
      recency: query.recency,
      specialtyGroup: query.specialtyGroup,
      country: query.country,
      seesPatientsOnly: query.seesPatients,
    });
    return sortDoctors(rows, query.sort);
  }, [
    doctors,
    effectiveUserLoc,
    activeDiseaseSlug,
    query.role,
    query.source,
    query.parentOnly,
    query.maxKm,
    query.workTypes,
    query.recency,
    query.specialtyGroup,
    query.country,
    query.seesPatients,
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

  // Count of doctors carrying a parent signal within the disease-scoped set,
  // measured BEFORE the parentOnly filter so the toggle label is stable.
  const recommendedCount = useMemo(() => {
    if (unknownDisease != null) {
      return 0;
    }
    return doctors.filter(
      (d) =>
        (!activeDiseaseSlug || d.diseases.includes(activeDiseaseSlug)) &&
        hasParentSignal(d),
    ).length;
  }, [doctors, activeDiseaseSlug, unknownDisease]);

  // Data-density gate for the clinical (specialty/country/sees-patients) filters: only expose
  // them once enough of the disease-scoped rows actually carry a VERIFIED specialty — otherwise a
  // near-empty filter would fake a clinical directory we don't have yet.
  const clinical = useMemo(() => {
    const scoped = doctors.filter(
      (d) => !activeDiseaseSlug || d.diseases.includes(activeDiseaseSlug),
    );
    const groups = new Set<string>();
    const countries = new Set<string>();
    let withSpecialty = 0;
    let seesPatients = 0;
    for (const d of scoped) {
      const g = specialtyGroupsOf(d);
      if (g.size > 0) withSpecialty += 1;
      g.forEach((x) => groups.add(x));
      if (d.country && /^[A-Z]{2}$/.test(d.country)) countries.add(d.country);
      if (d.reachability === "sees_patients") seesPatients += 1;
    }
    const ratio = scoped.length > 0 ? withSpecialty / scoped.length : 0;
    // Threshold intentionally low (5%) for a rare disease: even a handful of verified surgeons is
    // exactly the value we want to expose, and every specialty shown is individually honest
    // (source badge). Set >0 so a disease with zero clinical data hides the facet entirely.
    const ready = withSpecialty >= 3 || ratio >= 0.05;
    return {
      ready,
      groups: [...groups].sort(),
      countries: [...countries].sort(),
      seesPatients,
    };
  }, [doctors, activeDiseaseSlug]);

  // Count of active "advanced" filters so we can badge the disclosure trigger.
  const advancedActiveCount = useMemo(() => {
    let n = 0;
    if (query.role != null) n += 1;
    if (query.recency != null) n += 1;
    if (query.workTypes.length > 0) n += 1;
    if (query.source !== "all") n += 1;
    if (query.parentOnly) n += 1;
    if (query.seesPatients) n += 1;
    return n;
  }, [query.role, query.recency, query.workTypes, query.source, query.parentOnly, query.seesPatients]);

  const [advancedOpen, setAdvancedOpen] = useState(false);

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
        <AddDoctorCta
          account={account}
          onOpen={() => setAddDoctorOpen(true)}
        />
        <div className="doctors-presets" role="group" aria-label="Quick filters for families">
          <span className="doctors-presets__hint">Start here:</span>
          {DOCTOR_PRESETS
            // Presets that need clinical data are hidden until the specialty axis has some.
            .filter((preset) => !preset.needsSpecialty || clinical.ready)
            .map((preset) => (
              <button
                key={preset.id}
                type="button"
                className="preset-chip"
                onClick={() => patchQuery(preset.patch)}
              >
                {preset.label}
              </button>
            ))}
        </div>
      </header>

      <div className="dfilters">
        {/* ── Primary row: disease + location + clinical facets + sort ── */}
        <div className="dfilters__primary">
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

          <LocationMenu
            value={query.loc}
            label={query.locLabel}
            maxKm={query.maxKm as DistanceMax}
            onChange={handleLocationChange}
            onPickRadius={(km) => patchQuery({ maxKm: km })}
          />

          {clinical.ready ? (
            <>
              <FilterMenu
                label="Specialty"
                value={query.specialtyGroup ?? "all"}
                options={[
                  { value: "all", label: "Any specialty" },
                  ...clinical.groups.map((g) => ({ value: g, label: g })),
                ]}
                onPick={(v) =>
                  patchQuery({ specialtyGroup: v === "all" ? null : v })
                }
              />
              {clinical.countries.length > 1 ? (
                <FilterMenu
                  label="Country"
                  value={query.country ?? "all"}
                  options={[
                    { value: "all", label: "Any country" },
                    ...clinical.countries.map((c) => ({ value: c, label: c })),
                  ]}
                  onPick={(v) => patchQuery({ country: v === "all" ? null : v })}
                />
              ) : null}
            </>
          ) : null}

          <FilterMenu
            label="Sort"
            value={query.sort}
            neutralValue="best"
            options={SORT_OPTIONS}
            onPick={(v) => patchQuery({ sort: v as DoctorsQuery["sort"] })}
          />

          {/* "More filters" disclosure trigger */}
          <button
            type="button"
            className={`dfilters__more-btn${advancedOpen ? " is-open" : ""}${advancedActiveCount > 0 ? " has-active" : ""}`}
            aria-expanded={advancedOpen}
            aria-controls="dfilters-advanced"
            onClick={() => setAdvancedOpen((o) => !o)}
          >
            {advancedActiveCount > 0
              ? `More filters (${advancedActiveCount})`
              : "More filters"}
            <span className={`fmenu__chev${advancedOpen ? " is-open" : ""}`} aria-hidden="true">
              ▾
            </span>
          </button>
        </div>

        {/* ── Advanced filters: hidden until expanded ── */}
        {advancedOpen ? (
          <div
            id="dfilters-advanced"
            className="dfilters__advanced"
            role="group"
            aria-label="Advanced filters"
          >
            <FilterMenu
              label="Disease experience"
              value={query.role ?? ROLE_FILTER_ALL}
              options={ROLE_FILTERS}
              onPick={(v) =>
                patchQuery({ role: v === ROLE_FILTER_ALL ? null : (v as PubmedRole) })
              }
            />
            <FilterMenu
              label="On the disease"
              value={query.recency ?? RECENCY_FILTER_ALL}
              options={RECENCY_FILTERS}
              onPick={(v) =>
                patchQuery({
                  recency: v === RECENCY_FILTER_ALL ? null : (v as DoctorsQuery["recency"]),
                })
              }
            />
            <FilterMenu
              label="Source"
              value={query.source}
              options={SOURCE_FILTERS}
              onPick={(v) => patchQuery({ source: v as SourceFilter })}
            />
            {clinical.ready ? (
              <button
                type="button"
                className={`toggle-chip${query.seesPatients ? " is-active" : ""}`}
                aria-pressed={query.seesPatients}
                onClick={() => patchQuery({ seesPatients: !query.seesPatients })}
                title="Show doctors who see patients (experts reachable for a consult are always kept)"
              >
                Sees patients
              </button>
            ) : null}
            <button
              type="button"
              className={`toggle-chip${query.parentOnly ? " is-active" : ""}`}
              aria-pressed={query.parentOnly}
              onClick={() => patchQuery({ parentOnly: !query.parentOnly })}
              title="Show only doctors recommended by parents"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill={query.parentOnly ? "currentColor" : "none"}
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z" />
              </svg>
              Recommended by parents ({recommendedCount})
            </button>
            <div
              className="dfilters__worktypes"
              role="group"
              aria-label="Type of work on the disease"
            >
              <span className="dfilters__worktypes-label">Type of work:</span>
              {WORK_TYPE_ORDER.map((w) => {
                const active = query.workTypes.includes(w);
                return (
                  <button
                    key={w}
                    type="button"
                    className={`toggle-chip${active ? " is-active" : ""}`}
                    aria-pressed={active}
                    onClick={() => toggleWorkType(w)}
                  >
                    {workTypeLabel(w)}
                  </button>
                );
              })}
            </div>
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
              {items.length > 0 ? (
                <p className="doctors-count">
                  {items.length} specialist{items.length === 1 ? "" : "s"}
                  {pageCount > 1 ? (
                    <>
                      {" · showing "}
                      {pageStart + 1}–{pageStart + visibleItems.length}
                    </>
                  ) : null}
                </p>
              ) : null}
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
              <Pagination
                page={safePage}
                pageCount={pageCount}
                onPage={(p) => patchQuery({ page: p })}
              />
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

      {addDoctorOpen ? (
        <AddDoctorModal
          onClose={() => setAddDoctorOpen(false)}
          initialDiseaseSlug={activeDiseaseSlug}
        />
      ) : null}
    </section>
  );
}

type AccountCtx = ReturnType<typeof useAccountContext>;

/**
 * "Recommend a doctor we're missing" entry. The render decision is the pure
 * {@link addDoctorCtaMode} gate (env-gated on VITE_AUTH0_DOMAIN):
 * - "hidden": Auth0 unset (today's behaviour) or signed-in non-contributor.
 * - "sign-in": Auth0 on, signed-out → sign-in CTA.
 * - "open-modal": Auth0 on, signed-in parent/superadmin → opens the modal.
 */
function AddDoctorCta({
  account,
  onOpen,
}: {
  account: AccountCtx;
  onOpen: () => void;
}) {
  const mode = addDoctorCtaMode({
    signInAvailable: account.signInAvailable,
    isAuthenticated: account.isAuthenticated,
    role: account.account?.role,
  });
  if (mode === "open-modal") {
    return (
      <div className="doctors-add-cta">
        <Button type="button" variant="ghost" onClick={onOpen}>
          Recommend a doctor we&rsquo;re missing
        </Button>
      </div>
    );
  }
  if (mode === "sign-in") {
    return (
      <div className="doctors-add-cta">
        <button type="button" className="link-btn" onClick={account.login}>
          Sign in to recommend a doctor we&rsquo;re missing
        </button>
      </div>
    );
  }
  return null;
}
