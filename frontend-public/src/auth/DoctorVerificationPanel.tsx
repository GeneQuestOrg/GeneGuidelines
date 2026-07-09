import { useEffect, useState } from "react";
import { ApiRequestError } from "../api/client";
import { repositories } from "../repositories";
import type { AccountRole, VerificationRequest } from "../types/account";

export interface DoctorVerificationPanelProps {
  /**
   * The signed-in user's role. Drives the copy so the panel reads correctly for
   * both an unverified `doctor` and an unverified `researcher`. Anything else
   * falls back to neutral "expert" wording.
   */
  role?: AccountRole | null;
}

/** Role-specific noun for the account being verified. */
function accountNoun(role: AccountRole | null | undefined): string {
  if (role === "doctor") {
    return "clinician";
  }
  if (role === "researcher") {
    return "researcher";
  }
  return "expert";
}

/** Turn a submission failure into a short, user-facing sentence. */
function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    switch (error.status) {
      case 400:
        return "Add at least one detail (ORCID, licence number, institution, or a note).";
      case 403:
        return "Verification is only available for doctor and researcher accounts.";
      case 409:
        return "You already have a verification request under review.";
      default:
        return error.message;
    }
  }
  return error instanceof Error
    ? error.message
    : "Could not submit your verification request.";
}

/**
 * Verification panel for an unverified doctor or researcher (shown in the
 * account menu and on the account page while `isPendingVerification` holds).
 *
 * It offers two hybrid paths to the expert layer:
 *
 * - **ORCID** — when configured (probed via `/api/account/orcid/status`), a
 *   "Verify with ORCID" button redirects to the ORCID authorize URL, which
 *   auto-verifies on return.
 * - **Manual review** — a small form (`orcid`, `license_no`, `institution`,
 *   `note`, all optional but at least one required) POSTs to
 *   `/api/account/verification-requests`. Once a request is pending it is shown
 *   read-only until a superadmin reviews it.
 */
export function DoctorVerificationPanel({ role }: DoctorVerificationPanelProps = {}) {
  const [orcidEnabled, setOrcidEnabled] = useState(false);
  const [orcidBusy, setOrcidBusy] = useState(false);
  const [orcidError, setOrcidError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [pendingRequest, setPendingRequest] = useState<VerificationRequest | null>(
    null,
  );

  const [orcid, setOrcid] = useState("");
  const [licenseNo, setLicenseNo] = useState("");
  const [institution, setInstitution] = useState("");
  const [note, setNote] = useState("");
  const [submitBusy, setSubmitBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const account = repositories().account;
      const [enabled, mine] = await Promise.all([
        account.orcidEnabled().catch(() => false),
        account.myVerificationRequests().catch(() => [] as VerificationRequest[]),
      ]);
      if (cancelled) {
        return;
      }
      setOrcidEnabled(enabled);
      setPendingRequest(mine.find((r) => r.status === "pending") ?? null);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const verifyWithOrcid = async () => {
    setOrcidBusy(true);
    setOrcidError(null);
    try {
      const url = await repositories().account.orcidLoginUrl();
      window.location.assign(url);
    } catch (e: unknown) {
      setOrcidError(
        e instanceof Error ? e.message : "Could not start ORCID verification.",
      );
      setOrcidBusy(false);
    }
  };

  const hasEvidence =
    orcid.trim().length > 0 ||
    licenseNo.trim().length > 0 ||
    institution.trim().length > 0 ||
    note.trim().length > 0;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!hasEvidence || submitBusy) {
      return;
    }
    setSubmitBusy(true);
    setSubmitError(null);
    try {
      const created = await repositories().account.submitVerificationRequest({
        orcid: orcid.trim() || undefined,
        licenseNo: licenseNo.trim() || undefined,
        institution: institution.trim() || undefined,
        note: note.trim() || undefined,
      });
      setPendingRequest(created);
      setOrcid("");
      setLicenseNo("");
      setInstitution("");
      setNote("");
    } catch (e: unknown) {
      setSubmitError(messageForError(e));
    } finally {
      setSubmitBusy(false);
    }
  };

  const noun = accountNoun(role);

  return (
    <div className="account-menu__section verification-panel">
      <p className="account-menu__pending">Verification pending</p>
      <p className="account-menu__section-note">
        Your {noun} account is being verified before you can rate AI suggestions or
        publish.
      </p>

      {orcidEnabled ? (
        <button
          type="button"
          className="account-menu__item"
          onClick={() => void verifyWithOrcid()}
          disabled={orcidBusy}
        >
          {orcidBusy ? "Redirecting…" : "Verify with ORCID"}
        </button>
      ) : null}
      {orcidError != null ? (
        <p className="account-menu__error" role="alert">
          {orcidError}
        </p>
      ) : null}

      {loading ? (
        <p className="account-menu__section-note">Checking your verification status…</p>
      ) : pendingRequest != null ? (
        <div className="verification-panel__submitted" role="status">
          <p className="verification-panel__submitted-title">
            Your details are under review
          </p>
          <p className="account-menu__section-note">
            A reviewer will confirm your {noun} account. You will be able to rate and
            publish once approved.
          </p>
        </div>
      ) : (
        <form className="verification-panel__form" onSubmit={(e) => void submit(e)}>
          <p className="account-menu__section-note">
            Or send us identity details for manual review. Provide at least one.
          </p>
          <label className="verification-panel__field">
            <span>ORCID iD</span>
            <input
              type="text"
              className="verification-panel__input"
              value={orcid}
              onChange={(e) => setOrcid(e.target.value)}
              placeholder="0000-0002-1825-0097"
              autoComplete="off"
            />
          </label>
          <label className="verification-panel__field">
            <span>Licence number</span>
            <input
              type="text"
              className="verification-panel__input"
              value={licenseNo}
              onChange={(e) => setLicenseNo(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="verification-panel__field">
            <span>Institution</span>
            <input
              type="text"
              className="verification-panel__input"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="verification-panel__field">
            <span>Note</span>
            <textarea
              className="verification-panel__input verification-panel__textarea"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder="Anything that helps us verify you."
            />
          </label>
          <button
            type="submit"
            className="account-menu__copy verification-panel__submit"
            disabled={!hasEvidence || submitBusy}
          >
            {submitBusy ? "Submitting…" : "Submit for review"}
          </button>
          {submitError != null ? (
            <p className="account-menu__error" role="alert">
              {submitError}
            </p>
          ) : null}
        </form>
      )}
    </div>
  );
}
