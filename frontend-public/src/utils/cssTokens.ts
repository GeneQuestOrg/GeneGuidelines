/**
 * Read a CSS custom property (design token) off the document root at runtime.
 *
 * Leaflet needs literal color strings for SVG markers and circle markers, so we
 * cannot point it at ``var(--token)``. Instead we resolve the token's computed
 * value once and hand Leaflet the concrete color, falling back to a literal hex
 * when the token is unavailable (e.g. SSR, jsdom/node test env, or a typo).
 */
export function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined" || document.documentElement == null) {
    return fallback;
  }
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value.length > 0 ? value : fallback;
}

/** Token names + literal fallbacks for the doctor-map role markers. */
export const ROLE_COLOR_TOKENS: Record<string, { token: string; fallback: string }> = {
  research_leader: { token: "--st-blue", fallback: "#2563eb" },
  research_participant: { token: "--ink-3", fallback: "#6b7280" },
  case_study_author: { token: "--ink-4", fallback: "#9ca3af" },
  unknown: { token: "--line-2", fallback: "#d1d5db" },
};

/** Token names + literal fallbacks for the "your location" marker. */
export const USER_MARKER_TOKENS = {
  stroke: { token: "--st-red", fallback: "#dc2626" },
  fill: { token: "--st-red", fallback: "#fca5a5" },
} as const;
