import { useCallback, useEffect, useState } from "react";
import { parsePath } from "./parsePath";
import { splitLocale, withLocalePrefix, type Locale } from "./locale";
import type { Route } from "./types";

interface RouterLocation {
  pathname: string;
  search: string;
}

function readLocation(): RouterLocation {
  return { pathname: window.location.pathname, search: window.location.search };
}

/** Rewrite legacy ``/add-disease`` bookmarks to ``/start-research`` (path form). */
function canonicalizePath(pathname: string): string {
  return pathname === "/add-disease" ? "/start-research" : pathname;
}

/**
 * Decide whether a click on (or inside) an anchor should be handled as a client-side
 * SPA navigation instead of a full page load. Returns the resolved same-origin URL, or
 * `null` when the browser's default behaviour must be preserved (new tab, download,
 * modified click, external host, in-page fragment, or an anchor whose own handler
 * already called `preventDefault`).
 */
function spaTargetForClick(e: MouseEvent): URL | null {
  if (e.defaultPrevented) {
    return null; // an anchor's own onClick already handled it (e.g. preventDefault + onNav)
  }
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
    return null; // let the browser open new tabs / windows for modified or non-left clicks
  }
  const target = e.target as Element | null;
  const anchor = target?.closest?.("a") as HTMLAnchorElement | null;
  if (anchor == null) {
    return null;
  }
  const href = anchor.getAttribute("href");
  if (href == null || href.startsWith("#")) {
    return null; // no href, or a pure in-page fragment → browser scrolls, never route
  }
  const targetAttr = anchor.getAttribute("target");
  if (targetAttr && targetAttr !== "_self") {
    return null; // target="_blank" and friends open elsewhere
  }
  if (anchor.hasAttribute("download")) {
    return null;
  }
  const rel = anchor.getAttribute("rel") ?? "";
  if (rel.split(/\s+/).includes("external")) {
    return null;
  }
  let url: URL;
  try {
    url = new URL(anchor.href, window.location.href);
  } catch {
    return null;
  }
  if (url.origin !== window.location.origin) {
    return null; // external host — real navigation
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return null; // mailto:, tel:, etc.
  }
  return url;
}

export interface HistoryRouter {
  route: Route;
  /** Current `location.search` (e.g. ``?disease=fd``) — the query source for URL-synced views. */
  search: string;
  /**
   * Active locale, parsed from the URL prefix (``/pl/…`` → ``pl``; unprefixed → ``en``).
   * The URL is the single source of truth for language.
   */
  locale: Locale;
  /**
   * Navigate to an in-app path. Callers pass the canonical (English, unprefixed)
   * path, e.g. ``/diseases/fd``; the active locale prefix is applied automatically,
   * so an in-app link keeps the visitor in their chosen language.
   */
  navigate: (path: string) => void;
  /** Switch language, staying on the current route (re-prefixes the URL). */
  setLocale: (locale: Locale) => void;
}

/**
 * History (path) router: real URLs the server and crawlers see (`/diseases/fd`), no
 * ``#`` fragment. Reads `location.pathname` + `location.search`, listens on `popstate`,
 * and installs ONE delegated document-level click handler so every existing `<a href="/…">`
 * navigates client-side (no full reload) without per-anchor wiring.
 */
export function useHistoryRouter(): HistoryRouter {
  const [loc, setLoc] = useState<RouterLocation>(() => {
    // Pure: canonicalize only the value used for the initial parse. The effect
    // below rewrites the actual URL bar (replaceState) once mounted.
    const initial = readLocation();
    return { pathname: canonicalizePath(initial.pathname), search: initial.search };
  });
  // The stored pathname carries the locale prefix; strip it for route parsing and
  // expose the parsed locale separately. English is the canonical, unprefixed space.
  const { locale, pathname: barePath } = splitLocale(loc.pathname);
  const route = parsePath(barePath, loc.search);

  const applyLocation = useCallback((fullPathname: string, search: string) => {
    const next = fullPathname + search;
    if (window.location.pathname + window.location.search !== next) {
      window.history.pushState(null, "", next);
    }
    setLoc({ pathname: fullPathname, search });
    window.scrollTo(0, 0);
  }, []);

  const navigate = useCallback(
    (path: string) => {
      const clean = path.startsWith("#") ? path.slice(1) : path;
      const url = new URL(clean, window.location.origin);
      // Drop any locale prefix the caller may have included, then re-apply the
      // locale currently in the address bar (the source of truth) so in-app links
      // stay in the visitor's chosen language.
      const { pathname: bare } = splitLocale(canonicalizePath(url.pathname));
      const activeLocale = splitLocale(window.location.pathname).locale;
      applyLocation(withLocalePrefix(bare, activeLocale), url.search);
    },
    [applyLocation],
  );

  const setLocale = useCallback(
    (next: Locale) => {
      const { pathname: bare } = splitLocale(canonicalizePath(window.location.pathname));
      applyLocation(withLocalePrefix(bare, next), window.location.search);
    },
    [applyLocation],
  );

  useEffect(() => {
    const syncFromLocation = () => {
      const current = readLocation();
      const canonical = canonicalizePath(current.pathname);
      if (canonical !== current.pathname) {
        window.history.replaceState(null, "", canonical + current.search);
        setLoc({ pathname: canonical, search: current.search });
        return;
      }
      setLoc(current);
    };
    // popstate covers browser Back/Forward AND the synthetic popstate the Auth0
    // redirect-callback dispatches after `history.replaceState` (which fires none).
    const onPopState = () => syncFromLocation();
    const onClick = (e: MouseEvent) => {
      const url = spaTargetForClick(e);
      if (url == null) {
        return;
      }
      e.preventDefault();
      navigate(url.pathname + url.search);
    };
    // Re-read once on mount in case the location changed between the initial
    // render and this effect (e.g. the legacy-hash shim in main.tsx).
    syncFromLocation();
    window.addEventListener("popstate", onPopState);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("popstate", onPopState);
      document.removeEventListener("click", onClick);
    };
  }, [navigate]);

  return { route, search: loc.search, locale, navigate, setLocale };
}
