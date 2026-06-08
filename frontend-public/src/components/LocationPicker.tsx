import { useEffect, useRef, useState } from "react";
import type { UserLocation } from "../router/types";
import { searchGeo, type GeoResult } from "../api/geo";

export interface LocationPickerProps {
  readonly value: UserLocation | null;
  readonly label: string | null;
  readonly onChange: (loc: UserLocation | null, label: string | null) => void;
}

const DEBOUNCE_MS = 350;

export function LocationPicker({ value, label, onChange }: LocationPickerProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<GeoResult[]>([]);
  const [open, setOpen] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.trim().length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await searchGeo(value.trim());
        setSuggestions(results);
        setOpen(results.length > 0);
      } catch {
        setSuggestions([]);
        setOpen(false);
        setGeoError("Location search failed. Please try again.");
      }
    }, DEBOUNCE_MS);
  }

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function handleSelect(r: GeoResult) {
    const shortLabel = r.displayName.split(",").slice(0, 2).join(",").trim();
    onChange({ lat: r.lat, lng: r.lng }, shortLabel);
    setQuery("");
    setSuggestions([]);
    setOpen(false);
    setGeoError(null);
  }

  function handleGeolocate() {
    if (!navigator.geolocation) {
      setGeoError("Geolocation not supported by your browser.");
      return;
    }
    setGeoLoading(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoLoading(false);
        onChange({ lat: pos.coords.latitude, lng: pos.coords.longitude }, "Your location");
      },
      () => {
        setGeoLoading(false);
        setGeoError("Location access denied or unavailable.");
      },
      { timeout: 8000 },
    );
  }

  function handleClear() {
    onChange(null, null);
    setQuery("");
    setGeoError(null);
  }

  return (
    <div className="loc-picker" ref={containerRef}>
      {value != null ? (
        <div className="loc-picker__active">
          <span className="loc-picker__badge">
            📍 {label ?? `${value.lat.toFixed(2)}, ${value.lng.toFixed(2)}`}
          </span>
          <button
            type="button"
            className="loc-picker__clear"
            onClick={handleClear}
            aria-label="Clear location"
          >
            ✕
          </button>
        </div>
      ) : (
        <div className="loc-picker__row">
          <div className="loc-picker__input-wrap">
            <input
              type="text"
              className="loc-picker__input filters__select"
              placeholder="City or country…"
              value={query}
              onChange={(e) => handleQueryChange(e.target.value)}
              onFocus={() => suggestions.length > 0 && setOpen(true)}
              aria-label="Search location"
              aria-autocomplete="list"
              aria-expanded={open}
            />
            {open && suggestions.length > 0 ? (
              <ul className="loc-picker__dropdown" role="listbox">
                {suggestions.map((r, i) => (
                  <li
                    key={i}
                    className="loc-picker__option"
                    role="option"
                    aria-selected={false}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      handleSelect(r);
                    }}
                  >
                    {r.displayName.split(",").slice(0, 3).join(",")}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <button
            type="button"
            className="loc-picker__geo-btn"
            onClick={handleGeolocate}
            disabled={geoLoading}
            title="Use my location"
            aria-label="Use my location"
          >
            {geoLoading ? "…" : "⊙"}
          </button>
        </div>
      )}
      {geoError != null ? (
        <p className="loc-picker__error">{geoError}</p>
      ) : null}
    </div>
  );
}
