import { useCallback, type ReactNode } from "react";
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  useAuth,
  useUser,
} from "@clerk/clerk-react";
import { AuthTokenProvider } from "./AuthTokenContext";
import { getClerkPublishableKey } from "./clerkConfig";

function ClerkTokenBridge({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn } = useAuth();
  const getSessionToken = useCallback(async () => {
    if (!isSignedIn) return null;
    return getToken();
  }, [getToken, isSignedIn]);
  return <AuthTokenProvider getToken={getSessionToken}>{children}</AuthTokenProvider>;
}

export function ClerkShell({ children }: { children: ReactNode }) {
  const key = getClerkPublishableKey();
  if (!key) {
    return <AuthTokenProvider getToken={async () => null}>{children}</AuthTokenProvider>;
  }
  return (
    <ClerkProvider publishableKey={key}>
      <ClerkTokenBridge>{children}</ClerkTokenBridge>
    </ClerkProvider>
  );
}

function clerkNotConfiguredHint(label: string) {
  return (
    <span className="hdr-actions__hint" title="Set VITE_CLERK_PUBLISHABLE_KEY to enable sign-in">
      {label} (Clerk not configured)
    </span>
  );
}

export function ClerkSignInButton() {
  const key = getClerkPublishableKey();
  if (!key) {
    return clerkNotConfiguredHint("Sign in");
  }
  return (
    <SignedOut>
      <SignInButton mode="modal">
        <button type="button" className="hdr-actions__btn hdr-actions__btn--primary">
          Sign in
        </button>
      </SignInButton>
    </SignedOut>
  );
}

export function ClerkSignUpButton() {
  const key = getClerkPublishableKey();
  if (!key) {
    return clerkNotConfiguredHint("Sign up");
  }
  return (
    <SignedOut>
      <SignUpButton mode="modal">
        <button type="button" className="hdr-actions__btn">
          Sign up
        </button>
      </SignUpButton>
    </SignedOut>
  );
}

export function ClerkUserMenu({ onAccount }: { onAccount: () => void }) {
  const { user } = useUser();
  const key = getClerkPublishableKey();
  if (!key) return null;
  return (
    <SignedIn>
      <button type="button" className="hdr-actions__btn" onClick={onAccount}>
        {user?.fullName ?? user?.primaryEmailAddress?.emailAddress ?? "Account"}
      </button>
    </SignedIn>
  );
}
