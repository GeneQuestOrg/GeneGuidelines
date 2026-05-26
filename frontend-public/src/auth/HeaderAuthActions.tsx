import { useEffect, useState } from "react";
import { SignInButton, SignUpButton, UserButton, useAuth } from "@clerk/clerk-react";
import { getClerkPublishableKey } from "./clerkConfig";
import { fetchMe } from "../api/account";

export interface HeaderAuthActionsProps {
  onNav: (path: string) => void;
}

function goToAccount(onNav: (path: string) => void) {
  onNav("/account");
}

function FallbackAuthButtons({ onNav }: HeaderAuthActionsProps) {
  return (
    <>
      <button type="button" className="hdr-actions__btn" onClick={() => goToAccount(onNav)}>
        Sign up
      </button>
      <button
        type="button"
        className="hdr-actions__btn hdr-actions__btn--primary"
        onClick={() => goToAccount(onNav)}
      >
        Sign in
      </button>
    </>
  );
}

function ClerkHeaderAuthButtons({ onNav }: HeaderAuthActionsProps) {
  const { isLoaded, isSignedIn } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (!isSignedIn) return;
    fetchMe()
      .then((me) => setUnreadCount(me.unread_notifications_count ?? 0))
      .catch(() => {});
  }, [isSignedIn]);

  if (!isLoaded) {
    return (
      <>
        <button type="button" className="hdr-actions__btn" disabled aria-busy="true">
          Sign up
        </button>
        <button
          type="button"
          className="hdr-actions__btn hdr-actions__btn--primary"
          disabled
          aria-busy="true"
        >
          Sign in
        </button>
      </>
    );
  }

  if (!isSignedIn) {
    return (
      <>
        <SignUpButton mode="modal">
          <button type="button" className="hdr-actions__btn">
            Sign up
          </button>
        </SignUpButton>
        <SignInButton mode="modal">
          <button type="button" className="hdr-actions__btn hdr-actions__btn--primary">
            Sign in
          </button>
        </SignInButton>
      </>
    );
  }

  return (
    <>
      <button type="button" className="hdr-actions__btn" onClick={() => goToAccount(onNav)}>
        Account
        {unreadCount > 0 ? (
          <sup
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minWidth: "1.1em",
              height: "1.1em",
              fontSize: "0.6em",
              fontWeight: 700,
              borderRadius: "999px",
              background: "var(--accent)",
              color: "var(--bg-elev, #fff)",
              marginLeft: "0.25em",
              verticalAlign: "super",
              padding: "0 0.25em",
            }}
            aria-label={`${unreadCount} unread notifications`}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </sup>
        ) : null}
      </button>
      <UserButton afterSignOutUrl="/" />
    </>
  );
}

/** Always-visible sign-in / sign-up controls for the public header. */
export function HeaderAuthActions({ onNav }: HeaderAuthActionsProps) {
  const key = getClerkPublishableKey();
  if (!key) {
    return <FallbackAuthButtons onNav={onNav} />;
  }
  return <ClerkHeaderAuthButtons onNav={onNav} />;
}
