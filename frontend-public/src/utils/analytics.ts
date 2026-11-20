/**
 * Named events for the self-hosted, cookieless Umami tracker (loaded by index.html only when the build sets VITE_UMAMI_WEBSITE_ID).
 *
 * Only a handful of actions are counted, the ones the FD parent test is judged on: printing the list of tests and sharing a disease page. No personal data goes into an event. Without the tracker every call is a no-op, and a tracker error can never break the action it reports.
 */
declare global {
  interface Window {
    umami?: { track: (event: string, data?: Record<string, string | number>) => void };
  }
}

export type AnalyticsEvent = "print-fd-tests" | "share-disease-link";

export function trackEvent(name: AnalyticsEvent, data?: Record<string, string | number>): void {
  try {
    window.umami?.track(name, data);
  } catch {
    // Analytics must never get in the way of the action being counted.
  }
}
