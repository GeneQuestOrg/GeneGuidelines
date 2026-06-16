import { useCallback, useEffect, useState } from "react";
import { isPreviewRole, type PreviewRole } from "../auth/resolveRole";
import { DEFAULT_CITY } from "../config/cities";

export interface TweaksState {
  previewRole: PreviewRole;
  userCity: string;
  radiusKm: number;
  accent: string;
  density: "comfortable" | "compact";
}

const STORAGE_KEY = "gg-tweaks";

export const TWEAK_DEFAULTS: TweaksState = {
  previewRole: "auto",
  userCity: DEFAULT_CITY,
  radiusKm: 600,
  accent: "oklch(0.48 0.07 195)",
  density: "comfortable",
};

export const ACCENT_OPTIONS: readonly string[] = [
  "oklch(0.48 0.07 195)",
  "oklch(0.45 0.10 265)",
  "oklch(0.55 0.10 70)",
  "oklch(0.55 0.10 15)",
] as const;

function readTweaks(): TweaksState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return TWEAK_DEFAULTS;
    }
    const parsed = JSON.parse(raw) as Partial<TweaksState>;
    return {
      ...TWEAK_DEFAULTS,
      ...parsed,
      density: parsed.density === "compact" ? "compact" : "comfortable",
      previewRole: isPreviewRole(parsed.previewRole) ? parsed.previewRole : "auto",
    };
  } catch {
    return TWEAK_DEFAULTS;
  }
}

function writeTweaks(tweaks: TweaksState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tweaks));
  } catch {
    // ignore
  }
}

export function useTweaks(): {
  tweaks: TweaksState;
  setTweak: <K extends keyof TweaksState>(key: K, value: TweaksState[K]) => void;
} {
  const [tweaks, setTweaks] = useState<TweaksState>(readTweaks);

  useEffect(() => {
    document.documentElement.style.setProperty("--accent", tweaks.accent);
    document.documentElement.dataset.density = tweaks.density;
  }, [tweaks.accent, tweaks.density]);

  const setTweak = useCallback(<K extends keyof TweaksState>(key: K, value: TweaksState[K]) => {
    setTweaks((prev) => {
      const next = { ...prev, [key]: value };
      writeTweaks(next);
      return next;
    });
  }, []);

  return { tweaks, setTweak };
}
