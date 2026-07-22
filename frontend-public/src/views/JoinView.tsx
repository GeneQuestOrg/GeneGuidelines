import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("account");
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
              e instanceof Error ? e.message : t("join.notFoundDefaultMessage"),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, t]);

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
            e instanceof Error ? e.message : t("join.acceptErrorDefaultMessage"),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [preview, isAuthenticated, accept, acceptInvite, token, t]);

  const acceptAndSignIn = () => {
    setPendingInviteToken(token);
    login();
  };

  if (preview.status === "loading") {
    return (
      <section className="page page--narrow join">
        <p className="page__loading">{t("join.loading")}</p>
      </section>
    );
  }

  if (preview.status === "error") {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">{t("join.notFoundTitle")}</h1>
        <p className="page__lead">{preview.message}</p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/")}>
            {t("join.goToGeneGuidelines")}
          </button>
        </p>
      </section>
    );
  }

  const { inviterDisplay, expired, used } = preview.preview;

  if (expired || used) {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">{t("join.invalidTitle")}</h1>
        <p className="page__lead">
          {expired ? t("join.expiredMessage") : t("join.usedMessage")}
        </p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/")}>
            {t("join.exploreCta")}
          </button>
        </p>
      </section>
    );
  }

  if (!signInAvailable) {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">{t("join.inviteTitle")}</h1>
        <p className="page__lead">
          {t("join.signupClosedMessage", { inviter: inviterDisplay })}
        </p>
      </section>
    );
  }

  if (accept === "accepted") {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">{t("join.welcomeTitle")}</h1>
        <p className="page__lead">{t("join.welcomeMessage")}</p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/")}>
            {t("join.goToGeneGuidelines")}
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => onNav("/account")}>
            {t("join.viewAccount")}
          </button>
        </p>
      </section>
    );
  }

  if (accept === "error") {
    return (
      <section className="page page--narrow join">
        <h1 className="page__title">{t("join.errorTitle")}</h1>
        <p className="page__lead" role="alert">
          {acceptError ?? t("join.errorDefaultMessage")}
        </p>
        <p className="page__actions">
          <button type="button" className="btn btn--primary" onClick={() => onNav("/account")}>
            {t("join.goToAccount")}
          </button>
        </p>
      </section>
    );
  }

  // Valid invite. Either signing in (CTA) or already signed in and accepting.
  return (
    <section className="page page--narrow join">
      <h1 className="page__title">{t("join.inviteTitle")}</h1>
      <p className="page__lead">
        <strong>{inviterDisplay}</strong> {t("join.inviteMessageSuffix")}
      </p>
      <p className="join__note">{t("join.verifyNote")}</p>
      {isAuthenticated ? (
        <p className="page__loading">{t("join.settingUp")}</p>
      ) : (
        <p className="page__actions">
          <button
            type="button"
            className="btn btn--primary"
            onClick={acceptAndSignIn}
            disabled={loading}
          >
            {t("join.signInCta")}
          </button>
        </p>
      )}
    </section>
  );
}
