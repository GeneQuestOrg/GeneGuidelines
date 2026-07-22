import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import type { UserLocation } from "../router/types";
import { clinicalTrialsUrl, trialHasCoords, type TrialWithDistance } from "../api/trials";
import { formatDistanceKm } from "../utils/geo";
import { cssVar, USER_MARKER_TOKENS } from "../utils/cssTokens";
import "../styles/doctors.css";

export interface TrialsMapProps {
  readonly trials: readonly TrialWithDistance[];
  readonly userLoc: UserLocation | null;
}

const MAP_CLUSTER_MAX_RADIUS_PX = 48;

/** Marker color tokens by recruitment status; falls back to the muted token. */
const STATUS_COLOR: Readonly<Record<string, { token: string; fallback: string }>> = {
  recruiting: { token: "--st-green", fallback: "#16a34a" },
  active_not_recruiting: { token: "--st-blue", fallback: "#2563eb" },
  completed: { token: "--ink-3", fallback: "#6b7280" },
};

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function statusColor(status: string): string {
  const entry = STATUS_COLOR[status] ?? STATUS_COLOR.completed;
  return cssVar(entry.token, entry.fallback);
}

function statusMarkerIcon(status: string): L.DivIcon {
  const color = statusColor(status);
  return L.divIcon({
    html: `<svg width="16" height="16" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><circle cx="8" cy="8" r="6.5" fill="${color}" stroke="white" stroke-width="2"/></svg>`,
    className: "map-role-icon",
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -10],
  });
}

function buildPopupHtml(trial: TrialWithDistance, t: TFunction): string {
  const dist =
    trial.km != null ? `<span class="map-popup__dist">${formatDistanceKm(trial.km)}</span>` : "";
  const place = [trial.city, trial.country].filter(Boolean).map((s) => esc(String(s))).join(", ");
  const href = clinicalTrialsUrl(trial.nct);
  return `
    <div class="map-popup">
      <div class="map-popup__name">${esc(trial.title)}</div>
      <div class="map-popup__spec">${esc(trial.sponsor)}</div>
      ${place ? `<div class="map-popup__inst">${place}</div>` : ""}
      <div class="map-popup__foot">
        <span class="tag tag--score">${esc(statusLabel(trial.status))}</span>
        <span class="tag tag--score">${esc(trial.phase)}</span>
        ${dist}
      </div>
      <a class="trial-card__cta" href="${href}" target="_blank" rel="noopener noreferrer">${esc(t("openOnClinicalTrials"))}</a>
    </div>`;
}

export function TrialsMap({ trials, userLoc }: TrialsMapProps) {
  const { t } = useTranslation("trials");
  const hostRef = useRef<HTMLDivElement | null>(null);
  const pinned = trials.filter(trialHasCoords);

  useEffect(() => {
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

    for (const trial of trials) {
      if (!trialHasCoords(trial)) continue;
      const latlng: L.LatLngExpression = [trial.lat as number, trial.lng as number];
      const marker = L.marker(latlng, { icon: statusMarkerIcon(trial.status) });
      marker.bindPopup(buildPopupHtml(trial, t), { maxWidth: 260 });
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
        .bindTooltip(t("yourLocation"), { direction: "top" })
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
  }, [trials, userLoc, t]);

  return (
    <aside className="doctors-map" aria-label={t("mapAriaLabel")}>
      <div className="map-stub">
        <div className="map-stub__head">
          <div className="map-legend">
            <span className="map-legend__dot" style={{ background: statusColor("recruiting") }} />
            {t("statusOptionRecruiting")}
            <span
              className="map-legend__dot"
              style={{ background: statusColor("active_not_recruiting") }}
            />
            {t("legendActive")}
            <span className="map-legend__dot" style={{ background: statusColor("completed") }} />
            {t("statusOptionCompleted")}
          </div>
          <span className="map-stub__count">
            {t("mapCount", { pinned: pinned.length, listed: trials.length })}
          </span>
        </div>
        <div ref={hostRef} className="doctors-leaflet" />
        <p className="map-stub__note">{t("mapNote")}</p>
      </div>
    </aside>
  );
}
