import { Badge, Button, Section } from "@gene-guidelines/ui";
import { useAccountContext } from "../auth/accountContext";
import { DoctorVerificationPanel } from "../auth/DoctorVerificationPanel";
import { isPendingVerification } from "../auth/roleOptions";
import type { AccountRole } from "../types/account";

export interface AccountViewProps {
  onNav: (path: string) => void;
  /** Opens the legacy sign-in modal (only used when Auth0 is unconfigured). */
  onSignIn: () => void;
}

/** Human-friendly labels for each role; falls back to the raw value. */
const ROLE_LABELS: Record<AccountRole, string> = {
  parent: "Patient / Family",
  doctor: "Doctor",
  researcher: "Researcher",
  superadmin: "Superadmin",
};

function roleLabel(role: AccountRole | null): string {
  if (role == null) {
    return "Not set yet";
  }
  return ROLE_LABELS[role] ?? role;
}

/** Canonical ORCID URL for a bare identifier (e.g. `0000-0002-1825-0097`). */
function orcidUrl(orcid: string): string {
  const id = orcid.trim().replace(/^https?:\/\/orcid\.org\//i, "");
  return `https://orcid.org/${id}`;
}

/**
 * Read-only profile page for the signed-in user. Driven by the real account
 * context (`MeAccount` / `GET /api/account/me`), so it mirrors what the header
 * account menu shows. Handles loading, unconfigured-auth, and signed-out states.
 */
export function AccountView({ onNav, onSignIn }: AccountViewProps) {
  const { signInAvailable, loading, isAuthenticated, account, login } =
    useAccountContext();

  if (loading) {
    return (
      <section className="page page--narrow">
        <h1 className="page__title">Your account</h1>
        <p className="page__loading">Loading your account…</p>
      </section>
    );
  }

  if (!isAuthenticated || account == null) {
    // In Auth0 mode we can start the login redirect directly; otherwise fall
    // back to the legacy sign-in modal (`onSignIn`).
    const startSignIn = signInAvailable ? login : onSignIn;
    return (
      <section className="page page--narrow">
        <h1 className="page__title">Your account</h1>
        <p className="page__lead">
          Sign in to save preferences, follow diseases, and (for clinicians) contribute
          guideline updates.
        </p>
        <p className="page__actions">
          <Button variant="primary" onClick={startSignIn}>
            Sign in or register
          </Button>
          <Button variant="ghost" onClick={() => onNav("/")}>
            Back home
          </Button>
        </p>
      </section>
    );
  }

  const pending = isPendingVerification(account.role, account.verified);

  return (
    <section className="page page--narrow">
      <h1 className="page__title">Your account</h1>
      <p className="page__lead">
        Your GeneGuidelines profile. This information comes from your account and is
        visible only to you.
      </p>

      <Section title="Profile">
        <dl className="account-dl">
          {account.displayName ? (
            <>
              <dt>Name</dt>
              <dd>{account.displayName}</dd>
            </>
          ) : null}

          <dt>Email</dt>
          <dd>{account.email}</dd>

          <dt>Role</dt>
          <dd>{roleLabel(account.role)}</dd>

          <dt>Status</dt>
          <dd>
            {account.verified ? (
              <Badge variant="ok">Verified</Badge>
            ) : pending ? (
              <Badge>Pending verification</Badge>
            ) : (
              <Badge>Unverified</Badge>
            )}
          </dd>

          {account.institution ? (
            <>
              <dt>Institution</dt>
              <dd>{account.institution}</dd>
            </>
          ) : null}

          {account.orcid ? (
            <>
              <dt>ORCID</dt>
              <dd>
                <a href={orcidUrl(account.orcid)} target="_blank" rel="noopener noreferrer">
                  {account.orcid}
                </a>
              </dd>
            </>
          ) : null}
        </dl>
      </Section>

      {pending ? (
        <Section title="Verification">
          <DoctorVerificationPanel role={account.role} />
        </Section>
      ) : null}

      <p className="page__actions">
        <Button variant="ghost" onClick={() => onNav("/")}>
          Back home
        </Button>
      </p>
    </section>
  );
}
