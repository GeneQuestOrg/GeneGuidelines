import { useEffect, useState } from "react";
import { useAccountContext } from "../auth/accountContext";
import {
  clearPendingInviteToken,
  setPendingInviteToken,
} from "../auth/pendingInvite";
import { repositories } from "../repositories";
import type { InvitePreview } from "../types/account";
import "./join.css";

export interface JoinViewProps {
  readonly token: string;
  readonly onNav: (path: string) => void;
}

type PreviewState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; preview: InvitePreview };

type AcceptState = "idle" | "accepting" | "accepted" | "error";

/**
 * Doctor-invite landing (`#/join/{token}`). Fetches the public preview, then:
 * - **Auth0 off** — explains the platform is not open for sign-up yet.
 * - **expired / used** — a clear dead-end message.
 * - **valid, signed out** — invitation copy + sign-in/sign-up CTA. The token is
 *   stashed so the post-login round-trip auto-accepts.
 * - **valid, signed in** — auto-accepts and shows the verification-pending state.
 */
export function JoinView({ token, onNav }: JoinViewProps) {
  const { signInAvailable, isAuthenticated, loading, login, acceptInvite } =
    useAccountContext();
  const [preview, setPreview] = useState<PreviewState>({ status: "loading" });
  const [accept, setAccept] = useState<AcceptState>("idle");
  const [acceptError, setAcceptError] = useState<string | null>(null);

  // Load the public preview once per token. An async tick before setState keeps
  // the react-hooks lint rule happy (same pattern as AccountProvider).
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      try {
        const p = await repositories().account.getInvitePreview(token);
        if (!cancelled) {
          setPreview({ status: "ready", preview: p });
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setPreview({
            status: "error",
            message:
              e instanceof Error ? e.message : "This invitation could not be found.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Once signed in on a valid invite, redeem the token automatically.
  useEffect(() => {
    if (
      preview.status !== "ready" ||
      preview.preview.expired ||
      preview.preview.used ||
      !isAuthenticated ||
      accept !== "idle"
    ) {
      return;
    }
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) {
        return;
      }
      setAccept("accepting");
      try {
        await acceptInvite(token);
        clearPendingInviteToken();
        if (!cancelled) {
          setAccept("accepted");
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setAccept("error");
          setAcceptError(
            e instanceof Error ? e.message : "Could not accept this invitation.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [preview, isAuthenticated, accept, acceptInvite, token]);

  const acceptAndSignIn = () => {
    setPendingInviteToken(token);
    login();
  };

  if (preview.status === "loading") {
    return (
      <section className="page page--narrow join">
        <p className="page__loading">Loading your invitation…</p>
      </section>
    );
  }

  if (preview.status === "error") {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">Invitation not found</h1>
        <p className="page__lead">{preview.message}</p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/")}>
            Go to GeneGuidelines
          </button>
        </p>
      </section>
    );
  }

  const { inviterDisplay, expired, used } = preview.preview;

  if (expired || used) {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">This invitation is no longer valid</h1>
        <p className="page__lead">
          {expired
            ? "This invitation has expired. Ask the person who invited you to send a new link."
            : "This invitation has already been used. If that wasn't you, ask for a fresh link."}
        </p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/")}>
            Explore GeneGuidelines
          </button>
        </p>
      </section>
    );
  }

  if (!signInAvailable) {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">You've been invited to GeneGuidelines</h1>
        <p className="page__lead">
          {inviterDisplay} invited you as a clinician. Sign-up isn't open in this
          environment yet — please check back soon.
        </p>
      </section>
    );
  }

  if (accept === "accepted") {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">You're in — welcome</h1>
        <p className="page__lead">
          Your clinician account is set up. Identity verification is pending; an
          administrator (or ORCID, where available) will confirm it shortly. You can
          start exploring guidelines now.
        </p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/")}>
            Go to GeneGuidelines
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => onNav("/account")}>
            View your account
          </button>
        </p>
      </section>
    );
  }

  if (accept === "error") {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">We couldn't complete your invitation</h1>
        <p className="page__lead" role="alert">
          {acceptError ?? "Something went wrong accepting this invitation."}
        </p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/account")}>
            Go to your account
          </button>
        </p>
      </section>
    );
  }

  // Valid invite. Either signing in (CTA) or already signed in and accepting.
  return (
    <section className="page page--narrow join">
      <h1 className="page__title">You've been invited to GeneGuidelines</h1>
      <p className="page__lead">
        <strong>{inviterDisplay}</strong> invited you to join as a clinician — to review
        and contribute to living clinical guidelines for rare genetic diseases.
      </p>
      <p className="join__note">
        Doctor accounts are verified before they can publish. You'll be set up as a
        clinician now; verification follows.
      </p>
      {isAuthenticated ? (
        <p className="page__loading">Setting up your clinician account…</p>
      ) : (
        <p className="page__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={acceptAndSignIn}
            disabled={loading}
          >
            Sign in or create your account
          </button>
        </p>
      )}
    </section>
  );
}
