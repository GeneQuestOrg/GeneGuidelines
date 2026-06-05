import { useCallback, useMemo, type ReactNode } from "react";
import { AuthTokenContext, type AuthTokenGetter } from "./authToken";

export function AuthTokenProvider({
  getToken,
  children,
}: {
  getToken: AuthTokenGetter;
  children: ReactNode;
}) {
  const stable = useCallback(async () => getToken(), [getToken]);
  const value = useMemo(() => stable, [stable]);
  return (
    <AuthTokenContext.Provider value={value}>{children}</AuthTokenContext.Provider>
  );
}
