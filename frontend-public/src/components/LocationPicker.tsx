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
  const abortRef = useRef<AbortController | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    };
  }, []);

  function handleQueryChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    abortRef.current?.abort();
    if (value.trim().length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const results = await searchGeo(value.trim(), controller.signal);
        if (controller.signal.aborted) return;
        setSuggestions(results);
        setOpen(results.length > 0);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
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
                {suggestions.map((r) => (
                  <li
                    key={r.displayName}
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
            title="Detect my location"
            aria-label="Detect my location"
          >
            {geoLoading ? (
              "…"
            ) : (
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="7" />
                <line x1="12" y1="1" x2="12" y2="4" />
                <line x1="12" y1="20" x2="12" y2="23" />
                <line x1="1" y1="12" x2="4" y2="12" />
                <line x1="20" y1="12" x2="23" y2="12" />
                <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
              </svg>
            )}
          </button>
        </div>
      )}
      {geoError != null ? (
        <p className="loc-picker__error">{geoError}</p>
      ) : null}
    </div>
  );
}
