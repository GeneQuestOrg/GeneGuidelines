import { useCallback, useEffect, useRef, useState } from "react";
import { parseHash } from "./parseHash";
import type { Route } from "./types";

function readHash(): string {
  return window.location.hash || "#/";
}

/** Rewrite legacy ``#/add-disease`` bookmarks to ``#/start-research``. */
function canonicalizeHash(raw: string): string {
  if (raw === "#/add-disease" || raw.startsWith("#/add-disease?")) {
    return raw.replace("#/add-disease", "#/start-research");
  }
  return raw;
}

export interface HashRouter {
  route: Route;
  hash: string;
  /** Navigate to a hash path (with or without leading `#`). */
  navigate: (path: string) => void;
}

export function useHashRouter(): HashRouter {
  const [hash, setHash] = useState(() => canonicalizeHash(readHash()));
  const route = parseHash(hash);
  const hashRef = useRef(hash);
  const scrollPositions = useRef(new Map<string, number>());

  useEffect(() => {
    const syncHash = () => {
      const canonical = canonicalizeHash(readHash());
      if (window.location.hash !== canonical) {
        window.history.replaceState(null, "", canonical);
      }
      const prevHash = hashRef.current;

      // Save the outgoing page's scroll before React re-renders.
      // hashchange fires synchronously before React commits the new view,
      // so window.scrollY here is still the leaving page's position.
      if (prevHash !== canonical) {
        scrollPositions.current.set(prevHash, window.scrollY);
      }

      hashRef.current = canonical;
      setHash(canonical);

      if (prevHash !== canonical) {
        const saved = scrollPositions.current.get(canonical) ?? 0;
        if (saved > 0) {
          // Bounded rAF retry: re-apply scrollTo each frame until we reach the
          // target or exhaust attempts (~250ms). Needed because the disease page
          // remounts and async data (doctors, therapies…) increases page height
          // after the initial render, so a single-frame attempt gets clamped.
          let attempts = 0;
          const MAX_ATTEMPTS = 15;
          const restore = () => {
            window.scrollTo(0, saved);
            attempts++;
            if (window.scrollY < saved - 10 && attempts < MAX_ATTEMPTS) {
              requestAnimationFrame(restore);
            }
          };
          requestAnimationFrame(restore);
        } else {
          window.scrollTo(0, 0);
        }
      }
    };
    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  const navigate = useCallback((path: string) => {
    const next = path.startsWith("#") ? path : `#${path}`;
    if (window.location.hash !== next) {
      // Scroll save is handled in syncHash (via prevHash at hashchange time).
      window.location.hash = next;
    } else {
      setHash(next);
      window.scrollTo(0, 0);
    }
  }, []);

  return { route, hash, navigate };
}
