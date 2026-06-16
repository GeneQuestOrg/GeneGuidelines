import { useCallback, useState } from "react";
import { ACCENT_OPTIONS, type TweaksState } from "../hooks/useTweaks";
import { CITY_NAMES } from "../config/cities";
import "./tweaks-panel.css";

const PANEL_VISIBLE_KEY = "gg-tweaks-ui-visible";

function readPanelVisible(): boolean {
  try {
    return localStorage.getItem(PANEL_VISIBLE_KEY) === "1";
  } catch {
    return false;
  }
}

function writePanelVisible(visible: boolean): void {
  try {
    localStorage.setItem(PANEL_VISIBLE_KEY, visible ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
}

export interface TweaksPanelProps {
  tweaks: TweaksState;
  onTweak: <K extends keyof TweaksState>(key: K, value: TweaksState[K]) => void;
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: ReadonlyArray<{ value: T; label: string }>;
  onChange: (v: T) => void;
}) {
  return (
    <div className="twk-row">
      <span>{label}</span>
      <div className="twk-seg" role="group" aria-label={label}>
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={value === opt.value ? "is-on" : undefined}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TweaksPanel({ tweaks, onTweak }: TweaksPanelProps) {
  const [panelOpen, setPanelOpen] = useState(readPanelVisible);

  const openPanel = useCallback(() => {
    setPanelOpen(true);
    writePanelVisible(true);
  }, []);

  const closePanel = useCallback(() => {
    setPanelOpen(false);
    writePanelVisible(false);
  }, []);

  if (!panelOpen) {
    return (
      <button
        type="button"
        className="twk-reopen"
        aria-label="Open developer tweaks panel"
        onClick={openPanel}
      >
        Tweaks
      </button>
    );
  }

  return (
    <aside className="twk-panel" aria-label="Developer tweaks">
      <div className="twk-panel__hd">
        <span>Tweaks (dev)</span>
        <button
          type="button"
          className="twk-panel__close"
          aria-label="Hide tweaks panel"
          onClick={closePanel}
        >
          ×
        </button>
      </div>
      <div className="twk-panel__body">
        <p className="twk-section">Viewer role (preview)</p>
        <Segmented
          label="Role"
          value={tweaks.previewRole}
          options={[
            { value: "auto", label: "Auto (auth)" },
            { value: "anon", label: "Anon" },
            { value: "parent", label: "Parent" },
            { value: "doctor", label: "Doctor" },
            { value: "doctor-unverified", label: "Doctor·unv." },
            { value: "researcher", label: "Researcher" },
          ]}
          onChange={(v) => onTweak("previewRole", v)}
        />

        <p className="twk-section">Location</p>
        <div className="twk-row">
          <label htmlFor="twk-city">City</label>
          <select
            id="twk-city"
            className="twk-row"
            value={tweaks.userCity}
            onChange={(e) => onTweak("userCity", e.target.value)}
          >
            {CITY_NAMES.map((city) => (
              <option key={city} value={city}>
                {city}
              </option>
            ))}
          </select>
        </div>
        <div className="twk-row">
          <label htmlFor="twk-radius">
            Radius ({tweaks.radiusKm} km)
          </label>
          <input
            id="twk-radius"
            type="range"
            min={50}
            max={2000}
            step={50}
            value={tweaks.radiusKm}
            onChange={(e) => onTweak("radiusKm", Number(e.target.value))}
          />
        </div>

        <p className="twk-section">Appearance</p>
        <div className="twk-row">
          <label htmlFor="twk-accent">Accent</label>
          <select
            id="twk-accent"
            value={tweaks.accent}
            onChange={(e) => onTweak("accent", e.target.value)}
          >
            {ACCENT_OPTIONS.map((color) => (
              <option key={color} value={color}>
                {color}
              </option>
            ))}
          </select>
        </div>
        <Segmented
          label="Density"
          value={tweaks.density}
          options={[
            { value: "comfortable", label: "Comfort" },
            { value: "compact", label: "Compact" },
          ]}
          onChange={(v) => onTweak("density", v)}
        />
      </div>
    </aside>
  );
}
