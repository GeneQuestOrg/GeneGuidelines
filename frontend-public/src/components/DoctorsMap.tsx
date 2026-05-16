import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import type { UserLocation } from "../router/types";
import type { DoctorWithDistance } from "../utils/doctorSort";
import "../styles/doctors.css";

export interface DoctorsMapProps {
  readonly doctors: readonly DoctorWithDistance[];
  readonly userLoc: UserLocation | null;
  readonly onNav: (path: string) => void;
}

const MAP_CLUSTER_MAX_RADIUS_PX = 48;

export function DoctorsMap({ doctors, userLoc, onNav }: DoctorsMapProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const pins = doctors.filter(
      (d) => Number.isFinite(d.lat) && Number.isFinite(d.lng),
    );
    const el = hostRef.current;
    if (el == null) {
      return undefined;
    }

    delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })
      ._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: markerIcon2x,
      iconUrl: markerIcon,
      shadowUrl: markerShadow,
    });

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

    for (const d of pins) {
      const latlng: L.LatLngExpression = [d.lat, d.lng];
      const m = L.marker(latlng);
      m.bindTooltip(`${d.name} · ${d.city}`, { direction: "top" });
      m.on("click", () => onNav(`/doctor/${d.slug}`));
      cluster.addLayer(m);
      bounds.extend(latlng);
      extended = true;
    }

    if (userLoc != null && Number.isFinite(userLoc.lat)) {
      const latlng: L.LatLngExpression = [userLoc.lat, userLoc.lng];
      L.circleMarker(latlng, {
        radius: 6,
        color: "#dc2626",
        weight: 2,
        fillColor: "#fca5a5",
        fillOpacity: 0.9,
      })
        .bindTooltip("Your approximate location", { direction: "top" })
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
  }, [doctors, onNav, userLoc]);

  const pinCount = doctors.filter(
    (d) => Number.isFinite(d.lat) && Number.isFinite(d.lng),
  ).length;

  return (
    <aside className="doctors-map" aria-label="Specialist map">
      <div className="map-stub">
        <div className="map-stub__head">
          <span>Map</span>
          <span className="map-stub__count">
            {pinCount} on map · {doctors.length} listed
          </span>
        </div>
        <div ref={hostRef} className="doctors-leaflet" />
        <p className="map-stub__note">
          OpenStreetMap tiles · markers cluster when you zoom out. Click a pin to
          open the profile.
        </p>
      </div>
    </aside>
  );
}
