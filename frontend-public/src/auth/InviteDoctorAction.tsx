import { useState } from "react";
import { repositories } from "../repositories";

/** Build the full shareable URL (`https://host/#/join/{token}`) from a path. */
function inviteUrlFromPath(urlPath: string): string {
  const { origin, pathname } = window.location;
  return `${origin}${pathname}#${urlPath}`;
}

/**
 * "Invite their doctor" action in the account menu (parents / superadmins).
 * Mints an invite and shows a copyable `#/join/{token}` URL the parent can send
 * to their clinician. The doctor signs in via that link and is set up as an
 * (unverified) clinician.
 */
export function InviteDoctorAction() {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const invite = await repositories().account.createInvite();
      setUrl(inviteUrlFromPath(invite.urlPath));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not create an invite link.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (url == null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="account-menu__section">
      <p className="account-menu__section-title">Invite your doctor</p>
      {url == null ? (
        <>
          <button
            type="button"
            className="account-menu__item"
            onClick={() => void create()}
            disabled={busy}
          >
            {busy ? "Creating link…" : "Create an invite link"}
          </button>
          {error != null ? (
            <p className="account-menu__error" role="alert">
              {error}
            </p>
          ) : null}
        </>
      ) : (
        <div className="account-menu__invite">
          <input
            type="text"
            className="account-menu__invite-url"
            value={url}
            readOnly
            onFocus={(e) => e.currentTarget.select()}
            aria-label="Invite link"
          />
          <button
            type="button"
            className="account-menu__copy"
            onClick={() => void copy()}
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}
    </div>
  );
}
