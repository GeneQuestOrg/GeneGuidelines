import { useEffect } from "react";
import { useAuthTokenGetter } from "./authToken";
import { registerAuthFetch } from "./registerAuthFetch";

/** Wires Clerk session tokens into the shared API client. */
export function AuthFetchRegistrar() {
  const getToken = useAuthTokenGetter();
  useEffect(() => {
    registerAuthFetch(getToken);
  }, [getToken]);
  return null;
}
