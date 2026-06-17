import { createContext, useContext } from "react";
import type { ViewAsRole } from "./viewAs";

export interface ViewAsContextValue {
  viewAs: ViewAsRole;
  setViewAs: (role: ViewAsRole) => void;
}

export const ViewAsContext = createContext<ViewAsContextValue | null>(null);

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
