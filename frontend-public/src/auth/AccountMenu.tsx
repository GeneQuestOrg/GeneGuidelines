import { useEffect, useRef, useState } from "react";
import { useAccountContext } from "./accountContext";
import { isPendingVerification } from "./roleOptions";
import "./account-menu.css";

const ROLE_LABELS: Record<string, string> = {
  parent: "Patient / Family",
  doctor: "Doctor",
  researcher: "Researcher",
  superadmin: "Superadmin",
};

/**
 * Header account control. Replaces the localStorage `authOpen`/AuthModal stub on
 * the Auth0 path. Renders nothing when Auth0 is unconfigured (the env gate), so
 * the header looks exactly as it does today.
 */
export function AccountMenu() {
  const { signInAvailable, isAuthenticated, account, login, logout, loading } =
    useAccountContext();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDoc = (e: MouseEvent) => {
      if (ref.current != null && !ref.current.contains(e.target as Node)) {
        setOpen(false);
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

  return (
    <div className="account-menu" ref={ref}>
      <button
        type="button"
        className="account-menu__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
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
            {pending ? (
              <span className="account-menu__pending">Verification pending</span>
            ) : null}
          </div>
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
