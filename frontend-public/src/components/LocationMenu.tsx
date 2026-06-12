import { useEffect, useRef, useState } from "react";
import type { UserLocation } from "../router/types";
import { LocationPicker } from "./LocationPicker";

/** Distance cap in km, or null for "no limit" (show everyone, nearest first). */
export type DistanceMax = 25 | 100 | 500 | null;

export interface LocationMenuProps {
  readonly value: UserLocation | null;
  readonly label: string | null;
  readonly maxKm: DistanceMax;
  readonly onChange: (loc: UserLocation | null, label: string | null) => void;
  readonly onPickRadius: (km: DistanceMax) => void;
}

const RADIUS_OPTIONS: readonly { value: DistanceMax; label: string }[] = [
  { value: 25, label: "25 km" },
  { value: 100, label: "100 km" },
  { value: 500, label: "500 km" },
  { value: null, label: "No limit" },
];

function radiusLabel(maxKm: DistanceMax): string {
  return maxKm == null ? "No limit" : `${maxKm} km`;
}

/**
 * Draft9-style location filter: a pill button (pin + "Location" + the chosen
 * place and radius) that opens a popover holding the existing LocationPicker
 * (free-text geo + GPS) plus radius option buttons. The button reads active
 * whenever a finite radius is set. Closes on outside mousedown + Escape.
 *
 * Outside-click only needs ``ref.contains(target)``: LocationPicker's own
 * suggestion dropdown is ``position: absolute`` *inside* this same wrapper, so
 * clicking a suggestion never registers as outside the popover.
 */
export function LocationMenu({
  value,
  label,
  maxKm,
  onChange,
  onPickRadius,
}: LocationMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const active = value != null && maxKm != null;
  const placeText = value != null ? label ?? "Your location" : "Anywhere";

  return (
    <div className="fmenu fmenu--loc" ref={ref}>
      <button
        type="button"
        className={`fmenu__btn${active ? " is-active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
        <span className="fmenu__label">Location</span>
        <span className="fmenu__value">
          {placeText} · {radiusLabel(maxKm)}
        </span>
        <span className={`fmenu__chev${open ? " is-open" : ""}`} aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <div className="fmenu__pop fmenu__pop--loc" role="dialog" aria-label="Location filter">
          <div className="locm__row">
            <span className="locm__lbl">Your location</span>
            <LocationPicker value={value} label={label} onChange={onChange} />
          </div>
          <div className="locm__row">
            <span className="locm__lbl">Radius</span>
            <div className="locm__rads">
              {RADIUS_OPTIONS.map((r) => (
                <button
                  key={String(r.value)}
                  type="button"
                  className={`locm__rad${maxKm === r.value ? " is-sel" : ""}`}
                  onClick={() => onPickRadius(r.value)}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <p className="locm__hint">
            Distance is measured to the doctor&rsquo;s nearest practice. &ldquo;No limit&rdquo;
            shows everyone, sorted nearest first.
          </p>
        </div>
      ) : null}
    </div>
  );
}
