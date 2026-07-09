import { useEffect, useRef, useState } from "react";
import { useAccountContext } from "./accountContext";
import { isPendingVerification } from "./roleOptions";
import { InviteDoctorAction } from "./InviteDoctorAction";
import { DoctorVerificationPanel } from "./DoctorVerificationPanel";
import { useViewAsContext } from "./viewAsContext";
import { VIEW_AS_OPTIONS, type ViewAsRole } from "./viewAs";
import {
  getAdminAppUrl,
  getLegacyOpsUrl,
  isLegacyOpsLinkVisible,
} from "../config/adminUrl";
import "./account-menu.css";

const ROLE_LABELS: Record<string, string> = {
  parent: "Patient / Family",
  doctor: "Doctor",
  researcher: "Researcher",
  superadmin: "Superadmin",
};

function initialsFromEmail(email: string): string {
  const local = email.split("@")[0] ?? "";
  const parts = local.split(/[._+-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

export interface AccountMenuProps {
  /** App navigation callback (hash paths, e.g. `/account`). */
  onNav?: (path: string) => void;
}

/**
 * Header account control. Replaces the localStorage `authOpen`/AuthModal stub on
 * the Auth0 path. Renders nothing when Auth0 is unconfigured (the env gate), so
 * the header looks exactly as it does today.
 */
export function AccountMenu({ onNav }: AccountMenuProps = {}) {
  const { signInAvailable, isAuthenticated, account, login, logout, loading } =
    useAccountContext();
  const { viewAs, setViewAs } = useViewAsContext();
  const [open, setOpen] = useState(false);
  const [viewAsOpen, setViewAsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDoc = (e: MouseEvent) => {
      if (ref.current != null && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setViewAsOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Env gate: no Auth0 tenant → no account UI at all.
  if (!signInAvailable) {
    return null;
  }

  if (!isAuthenticated) {
    return (
      <button
        type="button"
        className="account-menu__signin"
        onClick={login}
        disabled={loading}
      >
        Sign in
      </button>
    );
  }

  const label = account?.email ?? "Account";
  const roleLabel = account?.role != null ? ROLE_LABELS[account.role] ?? account.role : null;
  const pending = account != null && isPendingVerification(account.role, account.verified);
  const canInvite = account?.role === "parent" || account?.role === "superadmin";
  const isSuperadmin = account?.role === "superadmin";
  const avatarInitials = initialsFromEmail(label);
  const adminUrl = isSuperadmin ? getAdminAppUrl() : null;
  const legacyUrl =
    isSuperadmin && isLegacyOpsLinkVisible() ? getLegacyOpsUrl() : null;

  return (
    <div className="account-menu" ref={ref}>
      <button
        type="button"
        className="account-menu__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="account-menu__avatar" aria-hidden="true">
          {avatarInitials}
        </span>
        <span className="account-menu__email">{label}</span>
        {pending ? <span className="account-menu__badge">Unverified</span> : null}
      </button>
      {open ? (
        <div className="account-menu__dropdown" role="menu">
          <div className="account-menu__identity">
            <span className="account-menu__identity-email">{account?.email}</span>
            {roleLabel != null ? (
              <span className="account-menu__identity-role">{roleLabel}</span>
            ) : null}
            {isSuperadmin && viewAs !== "auto" ? (
              <span className="account-menu__identity-role">
                Viewing as: {VIEW_AS_OPTIONS.find((o) => o.value === viewAs)?.label ?? viewAs}
              </span>
            ) : null}
          </div>
          {pending ? <DoctorVerificationPanel role={account?.role ?? null} /> : null}
          {canInvite ? <InviteDoctorAction /> : null}
          {onNav != null ? (
            <button
              type="button"
              role="menuitem"
              className="account-menu__item"
              onClick={() => {
                setOpen(false);
                onNav("/account");
              }}
            >
              Profile
            </button>
          ) : null}
          {adminUrl != null ? (
            <a
              href={adminUrl}
              className="account-menu__item"
              role="menuitem"
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
            >
              Admin app
            </a>
          ) : null}
          {legacyUrl != null ? (
            <a
              href={legacyUrl}
              className="account-menu__item"
              role="menuitem"
              target="_blank"
              rel="noopener noreferrer"
              title="Full workflow editor until migration to the new admin app completes"
              onClick={() => setOpen(false)}
            >
              Legacy ops
            </a>
          ) : null}
          {isSuperadmin ? (
            <div className="account-menu__section">
              <button
                type="button"
                className="account-menu__item account-menu__item--submenu"
                aria-expanded={viewAsOpen}
                onClick={() => setViewAsOpen((v) => !v)}
              >
                View as…
                <span className="account-menu__chevron" aria-hidden="true">
                  {viewAsOpen ? "▾" : "▸"}
                </span>
              </button>
              {viewAsOpen ? (
                <div className="account-menu__submenu" role="group">
                  {VIEW_AS_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      role="menuitemradio"
                      aria-checked={viewAs === opt.value}
                      className={
                        "account-menu__item account-menu__item--nested" +
                        (viewAs === opt.value ? " is-active" : "")
                      }
                      onClick={() => {
                        setViewAs(opt.value as ViewAsRole);
                        setViewAsOpen(false);
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="account-menu__item"
            onClick={() => {
              setOpen(false);
              logout();
            }}
          >
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
