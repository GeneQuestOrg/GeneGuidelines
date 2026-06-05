import type { ReactNode } from "react";
import { RedirectToSignIn, SignedIn, SignedOut } from "@clerk/clerk-react";
import { isClerkEnabled } from "./clerkConfig";

export interface RequireSignedInProps {
  children: ReactNode;
  fallback?: ReactNode;
}

/** Gate research routes when Clerk is configured. */
export function RequireSignedIn({ children, fallback }: RequireSignedInProps) {
  if (!isClerkEnabled()) {
    return <>{children}</>;
  }
  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut>{fallback ?? <RedirectToSignIn />}</SignedOut>
    </>
  );
}
