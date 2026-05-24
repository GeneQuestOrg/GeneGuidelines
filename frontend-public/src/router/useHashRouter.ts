import { useCallback, useEffect, useState } from "react";
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

  useEffect(() => {
    const syncHash = () => {
      const canonical = canonicalizeHash(readHash());
      if (window.location.hash !== canonical) {
        window.history.replaceState(null, "", canonical);
      }
      setHash(canonical);
      window.scrollTo(0, 0);
    };
    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  const navigate = useCallback((path: string) => {
    const next = path.startsWith("#") ? path : `#${path}`;
    if (window.location.hash !== next) {
      window.location.hash = next;
    } else {
      setHash(next);
      window.scrollTo(0, 0);
    }
  }, []);

  return { route, hash, navigate };
}
