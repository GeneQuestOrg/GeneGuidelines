import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Badge, Button, Section } from "@gene-guidelines/ui";
import { useAccountContext } from "../auth/accountContext";
import { isPendingVerification } from "../auth/roleOptions";
import type { AccountRole } from "../types/account";

export interface AccountViewProps {
  onNav: (path: string) => void;
  /** Opens the legacy sign-in modal (only used when Auth0 is unconfigured). */
  onSignIn: () => void;
}

/** Human-friendly labels for each role; falls back to the raw value. */
function roleLabel(role: AccountRole | null, t: TFunction): string {
  if (role == null) {
    return t("account.role.notSet");
  }
  const roleLabels: Record<AccountRole, string> = {
    parent: t("account.role.parent"),
    doctor: t("account.role.doctor"),
    researcher: t("account.role.researcher"),
    superadmin: t("account.role.superadmin"),
  };
  return roleLabels[role] ?? role;
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
  const { t } = useTranslation("account");
  const { signInAvailable, loading, isAuthenticated, account, login } =
    useAccountContext();

  if (loading) {
    return (
      <section className="page page--narrow">
        <h1 className="page__title">{t("account.title")}</h1>
        <p className="page__loading">{t("account.loading")}</p>
      </section>
    );
  }

  if (!isAuthenticated || account == null) {
    // In Auth0 mode we can start the login redirect directly; otherwise fall
    // back to the legacy sign-in modal (`onSignIn`).
    const startSignIn = signInAvailable ? login : onSignIn;
    return (
      <section className="page page--narrow">
        <h1 className="page__title">{t("account.title")}</h1>
        <p className="page__lead">{t("account.signedOutLead")}</p>
        <p className="page__actions">
          <Button variant="primary" onClick={startSignIn}>
            {t("account.signInCta")}
          </Button>
          <Button variant="ghost" onClick={() => onNav("/")}>
            {t("account.backHome")}
          </Button>
        </p>
      </section>
    );
  }

  const pending = isPendingVerification(account.role, account.verified);

  return (
    <section className="page page--narrow">
      <h1 className="page__title">{t("account.title")}</h1>
      <p className="page__lead">{t("account.lead")}</p>

      <Section title={t("account.profileTitle")}>
        <dl className="account-dl">
          {account.displayName ? (
            <>
              <dt>{t("account.labelName")}</dt>
              <dd>{account.displayName}</dd>
            </>
          ) : null}

          <dt>{t("account.labelEmail")}</dt>
          <dd>{account.email}</dd>

          <dt>{t("account.labelRole")}</dt>
          <dd>{roleLabel(account.role, t)}</dd>

          <dt>{t("account.labelStatus")}</dt>
          <dd>
            {account.verified ? (
              <Badge variant="ok">{t("account.status.verified")}</Badge>
            ) : pending ? (
              <Badge>{t("account.status.pending")}</Badge>
            ) : (
              <Badge>{t("account.status.unverified")}</Badge>
            )}
          </dd>

          {account.institution ? (
            <>
              <dt>{t("account.labelInstitution")}</dt>
              <dd>{account.institution}</dd>
            </>
          ) : null}

          {account.orcid ? (
            <>
              <dt>{t("account.labelOrcid")}</dt>
              <dd>
                <a href={orcidUrl(account.orcid)} target="_blank" rel="noopener noreferrer">
                  {account.orcid}
                </a>
              </dd>
            </>
          ) : null}
        </dl>
      </Section>

      <p className="page__actions">
        <Button variant="ghost" onClick={() => onNav("/")}>
          {t("account.backHome")}
        </Button>
      </p>
    </section>
  );
}
