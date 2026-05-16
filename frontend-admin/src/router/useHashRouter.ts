import { useCallback, useEffect, useState } from "react";
import { parseHash } from "./parseHash";
import type { AdminRoute } from "./types";

function readHash(): string {
  return window.location.hash || "#/runs";
}

export function useHashRouter(): {
  route: AdminRoute;
  navigate: (path: string) => void;
} {
  const [hash, setHash] = useState(readHash);
  const route = parseHash(hash);

  useEffect(() => {
    const onHashChange = () => {
      setHash(readHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
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

  return { route, navigate };
}
