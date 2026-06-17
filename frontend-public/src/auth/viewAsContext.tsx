import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { readViewAs, writeViewAs, type ViewAsRole } from "./viewAs";

interface ViewAsContextValue {
  viewAs: ViewAsRole;
  setViewAs: (role: ViewAsRole) => void;
}

const ViewAsContext = createContext<ViewAsContextValue | null>(null);

export function ViewAsProvider({ children }: { children: ReactNode }) {
  const [viewAs, setViewAsState] = useState<ViewAsRole>(readViewAs);
  const setViewAs = useCallback((role: ViewAsRole) => {
    writeViewAs(role);
    setViewAsState(role);
  }, []);
  const value = useMemo(() => ({ viewAs, setViewAs }), [viewAs, setViewAs]);
  return <ViewAsContext.Provider value={value}>{children}</ViewAsContext.Provider>;
}

export function useViewAsContext(): ViewAsContextValue {
  const ctx = useContext(ViewAsContext);
  if (ctx == null) {
    throw new Error("useViewAsContext must be used within ViewAsProvider");
  }
  return ctx;
}

/** Optional hook for components that may render outside the provider (returns auto). */
export function useViewAsOptional(): ViewAsContextValue {
  const ctx = useContext(ViewAsContext);
  return ctx ?? { viewAs: "auto", setViewAs: () => {} };
}
