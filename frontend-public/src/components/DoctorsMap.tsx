import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import type { UserLocation } from "../router/types";
import type { Practice } from "../types/doctor";
import type { DoctorWithDistance } from "../utils/doctorSort";
import { pubmedRoleLabel } from "../utils/doctorLabels";
import { formatDistanceKm } from "../utils/geo";
import { practicePins } from "../utils/practices";
import { cssVar, ROLE_COLOR_TOKENS, USER_MARKER_TOKENS } from "../utils/cssTokens";
import "../styles/doctors.css";

export interface DoctorsMapProps {
  readonly doctors: readonly DoctorWithDistance[];
  readonly userLoc: UserLocation | null;
  readonly onNav: (path: string) => void;
}

const MAP_CLUSTER_MAX_RADIUS_PX = 48;

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const VALID_PUBMED_ROLES = new Set(Object.keys(ROLE_COLOR_TOKENS));

function safeRole(role: string): string {
  return VALID_PUBMED_ROLES.has(role) ? role : "unknown";
}

/** Resolve a role's marker color from the design token, with a literal fallback. */
function roleColor(role: string): string {
  const entry = ROLE_COLOR_TOKENS[safeRole(role)];
  return cssVar(entry.token, entry.fallback);
}

function roleMarkerIcon(role: string): L.DivIcon {
  const color = roleColor(role);
  return L.divIcon({
    html: `<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="6.5" fill="${color}" stroke="white" stroke-width="2"/></svg>`,
    className: "map-role-icon",
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -10],
  });
}

function buildPopupHtml(
  d: DoctorWithDistance,
  practice: Practice,
  specialtyNotVerifiedLabel: string,
  roleLabel: string,
): string {
  const validatedRole = safeRole(d.pubmedRole);
  const dist = d.km != null ? `<span class="map-popup__dist">${formatDistanceKm(d.km)}</span>` : "";
  const practiceLine = `${esc(practice.name)} · ${esc(practice.type)}`;
  return `
    <div class="map-popup">
      <div class="map-popup__name">${esc(d.name)}</div>
      <div class="map-popup__spec">${d.specialty?.trim() ? esc(d.specialty) : esc(specialtyNotVerifiedLabel)}</div>
      <div class="map-popup__practice">${practiceLine}</div>
      <div class="map-popup__inst">${esc(practice.city)}, ${esc(d.country)}</div>
      <div class="map-popup__foot">
        <span class="tag tag--role tag--${esc(validatedRole)}">${esc(roleLabel)}</span>
        <span class="tag tag--score">PubMed <b>${esc(String(d.score))}</b></span>
        ${dist}
      </div>
    </div>`;
}

export function DoctorsMap({ doctors, userLoc, onNav }: DoctorsMapProps) {
  const { t } = useTranslation("doctors-page");
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const pins = practicePins(doctors);
    const el = hostRef.current;
    if (el == null) {
      return undefined;
    }

    const map = L.map(el).setView([54, 15], 3);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    const cluster = L.markerClusterGroup({
      maxClusterRadius: MAP_CLUSTER_MAX_RADIUS_PX,
      chunkedLoading: true,
    });

    const bounds = L.latLngBounds([] as L.LatLngExpression[]);
    let extended = false;

    for (const { doctor: d, practice } of pins) {
      // practicePins() already dropped pairs with non-finite coordinates, so these are real numbers.
      const latlng: L.LatLngExpression = [practice.lat as number, practice.lng as number];
      const marker = L.marker(latlng, { icon: roleMarkerIcon(d.pubmedRole) });
      marker.bindPopup(
        buildPopupHtml(
          d,
          practice,
          t("map.specialtyNotVerified"),
          t(`common:${pubmedRoleLabel(d.pubmedRole)}`),
        ),
        { maxWidth: 240 },
      );
      marker.on("popupopen", () => {
        const btn = marker.getPopup()?.getElement()?.querySelector<HTMLElement>(".map-popup");
        btn?.addEventListener("click", () => {
          onNav(`/doctor/${d.slug}`);
          marker.closePopup();
        }, { once: true });
      });
      cluster.addLayer(marker);
      bounds.extend(latlng);
      extended = true;
    }

    if (userLoc != null && Number.isFinite(userLoc.lat)) {
      const latlng: L.LatLngExpression = [userLoc.lat, userLoc.lng];
      L.circleMarker(latlng, {
        radius: 7,
        color: cssVar(USER_MARKER_TOKENS.stroke.token, USER_MARKER_TOKENS.stroke.fallback),
        weight: 2,
        fillColor: cssVar(USER_MARKER_TOKENS.fill.token, USER_MARKER_TOKENS.fill.fallback),
        fillOpacity: 0.9,
      })
        .bindTooltip(t("map.yourLocation"), { direction: "top" })
        .addTo(map);
      bounds.extend(latlng);
      extended = true;
    }

    map.addLayer(cluster);
    if (extended && bounds.isValid()) {
      map.fitBounds(bounds.pad(0.15));
    }

    return () => {
      map.remove();
    };
  }, [doctors, onNav, userLoc, t]);

  const pinCount = practicePins(doctors).length;

  return (
    <aside className="doctors-map" aria-label={t("map.ariaLabel")}>
      <div className="map-stub">
        <div className="map-stub__head">
          <div className="map-legend">
            <span className="map-legend__dot map-legend__dot--research_leader" />
            {t("map.legend.researchLeader")}
            <span className="map-legend__dot map-legend__dot--research_participant" />
            {t("map.legend.researchParticipant")}
            <span className="map-legend__dot map-legend__dot--case_study_author" />
            {t("map.legend.caseStudyAuthor")}
          </div>
          <span className="map-stub__count">
            {t("map.count", { pinCount, total: doctors.length })}
          </span>
        </div>
        <div ref={hostRef} className="doctors-leaflet" />
        <p className="map-stub__note">{t("map.note")}</p>
      </div>
    </aside>
  );
}
