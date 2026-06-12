import { useEffect, useState } from "react";
import { repositories } from "../repositories";

/**
 * Verification panel for an unverified doctor (shown in the account menu when
 * `role === "doctor" && !verified`). Always states that verification is pending;
 * when ORCID is configured (probed via `/api/account/orcid/status`) it offers a
 * "Verify with ORCID" button that redirects to the ORCID authorize URL. When
 * ORCID is off the button is hidden — an administrator approves instead.
 */
export function DoctorVerificationPanel() {
  const [orcidEnabled, setOrcidEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      try {
        const enabled = await repositories().account.orcidEnabled();
        if (!cancelled) {
          setOrcidEnabled(enabled);
        }
      } catch {
        if (!cancelled) {
          setOrcidEnabled(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      const url = await repositories().account.orcidLoginUrl();
      window.location.assign(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not start ORCID verification.");
      setBusy(false);
    }
  };

  return (
    <div className="account-menu__section">
      <p className="account-menu__pending">Verification pending</p>
      <p className="account-menu__section-note">
        Your clinician account is being verified before you can publish.
      </p>
      {orcidEnabled ? (
        <button
          type="button"
          className="account-menu__item"
          onClick={() => void verify()}
          disabled={busy}
        >
          {busy ? "Redirecting…" : "Verify with ORCID"}
        </button>
      ) : null}
      {error != null ? (
        <p className="account-menu__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
