import { useCallback, useState } from "react";
import type { AudienceView } from "../router/types";
import { isClerkEnabled } from "../auth/clerkConfig";
import { patchAudienceView } from "../api/account";

const STORAGE_KEY = "gg-view";

function readView(fallback: AudienceView): AudienceView {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "parent" || raw === "doctor") {
      return raw;
    }
  } catch {
    // ignore
  }
  return fallback;
}

export function useAudienceView(defaultView: AudienceView): {
  view: AudienceView;
  setView: (next: AudienceView) => void;
} {
  const [view, setViewState] = useState<AudienceView>(() => readView(defaultView));

  const setView = useCallback((next: AudienceView) => {
    setViewState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
    if (isClerkEnabled()) {
      patchAudienceView(next).catch(() => {});
    }
  }, []);

  return { view, setView };
}
