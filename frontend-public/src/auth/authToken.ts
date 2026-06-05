import { createContext, useContext } from "react";

export type AuthTokenGetter = () => Promise<string | null>;

export const AuthTokenContext = createContext<AuthTokenGetter | null>(null);

export function useAuthTokenGetter(): AuthTokenGetter {
  const getter = useContext(AuthTokenContext);
  return getter ?? (async () => null);
}
