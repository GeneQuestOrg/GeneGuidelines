import { SignedIn, useUser } from "@clerk/clerk-react";
import {
  getAdminAppUrl,
  getLegacyOpsUrl,
  isAdminLinkVisible,
  isLegacyOpsLinkVisible,
} from "../config/adminUrl";
import { isClerkAdmin } from "../auth/clerkRole";
import { isClerkEnabled } from "../auth/clerkConfig";
import "./admin-app-link.css";

function AdminAppLinkContent() {
  if (!isAdminLinkVisible()) {
    return null;
  }

  const adminUrl = getAdminAppUrl();
  if (adminUrl == null) {
    return null;
  }

  const legacyUrl = isLegacyOpsLinkVisible() ? getLegacyOpsUrl() : null;

  return (
    <div className="admin-app-link">
      <a
        href={adminUrl}
        className="hdr-actions__btn admin-app-link__primary"
        target="_blank"
        rel="noopener noreferrer"
      >
        Admin
      </a>
      {legacyUrl != null ? (
        <a
          href={legacyUrl}
          className="hdr-actions__btn admin-app-link__legacy"
          target="_blank"
          rel="noopener noreferrer"
          title="Full workflow editor until migration to the new admin app completes"
        >
          Legacy ops
        </a>
      ) : null}
    </div>
  );
}

function ClerkAwareAdminAppLink() {
  const { user, isLoaded } = useUser();
  if (!isLoaded) return null;
  if (!isClerkAdmin(user)) return null;
  return <AdminAppLinkContent />;
}

export function AdminAppLink() {
  if (!isClerkEnabled()) {
    return <AdminAppLinkContent />;
  }
  return (
    <SignedIn>
      <ClerkAwareAdminAppLink />
    </SignedIn>
  );
}
