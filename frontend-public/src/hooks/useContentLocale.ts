import { useEffect, useState } from "react";
import { DEFAULT_LOCALE, readLocaleFromLocation, type Locale } from "../router/locale";
import { LOCATION_CHANGED_EVENT } from "../router/locationEvent";

/**
 * The content locale, as a reactive value.
 *
 * Every hook that fetches translatable content must include this in its effect
 * dependencies. `apiGet` appends `?locale=` by reading the URL at call time, so a
 * fetch already asks for the right language — but nothing re-ran the fetch when
 * the language changed. Switching to Polish rewrote the URL and swapped the UI
 * strings (i18next re-renders on its own), while the synthesis, the source shelf,
 * the doctor list and everything else kept serving whatever language they were
 * first loaded in. That is the "I clicked PL and the article stayed English" bug.
 *
 * Reads the locale from the path rather than from a stored preference, so the URL
 * stays the single source of truth and a shared `/pl/...` link opens in Polish.
 */
export function useContentLocale(): Locale {
  const [locale, setLocale] = useState<Locale>(() =>
    typeof window === "undefined" ? DEFAULT_LOCALE : readLocaleFromLocation(),
  );

  useEffect(() => {
    const sync = () => setLocale(readLocaleFromLocation());
    // popstate covers back/forward; the custom event covers in-app pushState
    // navigation, which fires no native event.
    window.addEventListener("popstate", sync);
    window.addEventListener(LOCATION_CHANGED_EVENT, sync);
    sync();
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(LOCATION_CHANGED_EVENT, sync);
    };
  }, []);

  return locale;
}
