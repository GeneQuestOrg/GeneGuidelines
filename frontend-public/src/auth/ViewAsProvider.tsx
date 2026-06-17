import { useCallback, useMemo, useState, type ReactNode } from "react";
import { readViewAs, writeViewAs, type ViewAsRole } from "./viewAs";
import { ViewAsContext } from "./viewAsContext";

export function ViewAsProvider({ children }: { children: ReactNode }) {
  const [viewAs, setViewAsState] = useState<ViewAsRole>(readViewAs);
  const setViewAs = useCallback((role: ViewAsRole) => {
    writeViewAs(role);
    setViewAsState(role);
  }, []);
  const value = useMemo(() => ({ viewAs, setViewAs }), [viewAs, setViewAs]);
  return <ViewAsContext.Provider value={value}>{children}</ViewAsContext.Provider>;
}
