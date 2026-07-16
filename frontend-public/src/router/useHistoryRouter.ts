import { useCallback, useEffect, useState } from "react";
import { parsePath } from "./parsePath";
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
  /** Navigate to an in-app path (with or without leading `#`, which is stripped). */
  navigate: (path: string) => void;
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
  const route = parsePath(loc.pathname, loc.search);

  const navigate = useCallback((path: string) => {
    const clean = path.startsWith("#") ? path.slice(1) : path;
    const url = new URL(clean, window.location.origin);
    const pathname = canonicalizePath(url.pathname);
    const next = pathname + url.search;
    if (window.location.pathname + window.location.search !== next) {
      window.history.pushState(null, "", next);
    }
    setLoc({ pathname, search: url.search });
    window.scrollTo(0, 0);
  }, []);

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

  return { route, search: loc.search, navigate };
}
