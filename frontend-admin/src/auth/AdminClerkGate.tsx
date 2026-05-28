import { useEffect, type ReactNode } from "react";
import {
  ClerkProvider,
  SignInButton,
  SignedIn,
  SignedOut,
  useAuth,
  useUser,
} from "@clerk/clerk-react";
import { Button } from "@gene-guidelines/ui";
import { registerOpsAuthTokenGetter } from "@gene-guidelines/ops";
import { isClerkAdmin } from "./clerkRole";
import { getClerkPublishableKey, isClerkEnabled } from "./clerkConfig";
import "./admin-gate.css";

function OpsAuthRegistrar() {
  const { getToken, isSignedIn } = useAuth();
  useEffect(() => {
    registerOpsAuthTokenGetter(async () => {
      if (!isSignedIn) return null;
      return getToken();
    });
  }, [getToken, isSignedIn]);
  return null;
}

function AdminGateScreen({ children }: { children: ReactNode }) {
  return <div className="admin-gate-screen">{children}</div>;
}

function AdminRoleGate({ children }: { children: ReactNode }) {
  const { user, isLoaded } = useUser();
  if (!isLoaded) {
    return (
      <AdminGateScreen>
        <section className="admin-gate" aria-busy="true" aria-live="polite">
          <p className="admin-gate__eyebrow">Operations</p>
          <h1>GeneGuidelines Admin</h1>
          <p className="admin-gate__loading">Loading session…</p>
        </section>
      </AdminGateScreen>
    );
  }
  if (!isClerkAdmin(user)) {
    return (
      <AdminGateScreen>
        <section className="admin-gate admin-gate--denied">
          <p className="admin-gate__eyebrow">Operations</p>
          <h1>Admin access required</h1>
          <p className="admin-gate__lead">
            Your account is signed in but does not have the <code>admin</code> role in Clerk
            public metadata.
          </p>
          <p className="admin-gate__hint">
            Ask an operator to set <code>{`{"role":"admin"}`}</code> on your user, then refresh
            this page.
          </p>
          <p className="admin-gate__footer">
            <a href="/">← Back to public site</a>
          </p>
        </section>
      </AdminGateScreen>
    );
  }
  return <>{children}</>;
}

function ClerkSignedInShell({ children }: { children: ReactNode }) {
  return (
    <>
      <OpsAuthRegistrar />
      <AdminRoleGate>{children}</AdminRoleGate>
    </>
  );
}

export function AdminClerkGate({ children }: { children: ReactNode }) {
  const key = getClerkPublishableKey();
  if (!isClerkEnabled() || !key) {
    return <>{children}</>;
  }
  return (
    <ClerkProvider publishableKey={key}>
      <SignedOut>
        <AdminGateScreen>
          <section className="admin-gate" aria-labelledby="admin-gate-title">
            <p className="admin-gate__eyebrow">Operations</p>
            <h1 id="admin-gate-title">GeneGuidelines Admin</h1>
            <p className="admin-gate__lead">
              Sign in with an existing account that already has the admin role in Clerk.
            </p>
            <p className="admin-gate__hint">
              Need access? Ask an operator to grant the admin role. New users can register on
              the public site first.
            </p>
            <div className="admin-gate__actions">
              <SignInButton mode="modal">
                <Button variant="primary" type="button">
                  Sign in
                </Button>
              </SignInButton>
            </div>
            <p className="admin-gate__footer">
              <a href="/">← Public site (sign up there)</a>
            </p>
          </section>
        </AdminGateScreen>
      </SignedOut>
      <SignedIn>
        <ClerkSignedInShell>{children}</ClerkSignedInShell>
      </SignedIn>
    </ClerkProvider>
  );
}
