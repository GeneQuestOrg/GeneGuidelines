/**
 * Event name the router dispatches after an in-app `pushState` navigation.
 *
 * `pushState` fires no native event, so anything outside the router that needs to
 * react to a URL change (notably `useContentLocale`, which re-fetches content when
 * the language prefix changes) has nothing to listen to. The router dispatches this
 * instead. Kept in its own module so listeners don't import the router hook and
 * create a cycle.
 */
export const LOCATION_CHANGED_EVENT = "gg:locationchange";

export function emitLocationChanged(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new Event(LOCATION_CHANGED_EVENT));
}
