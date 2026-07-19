import { useRef, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { AppHeader, AuthModal, useAccount, type NavLink } from "@gene-guidelines/ui";
import type { Account } from "@gene-guidelines/ui";
import type { Route } from "../router/types";
import type { Locale } from "../router/locale";
import { useAccountContext } from "../auth/accountContext";
import { AccountMenu } from "../auth/AccountMenu";
import { LocaleSwitcher } from "./LocaleSwitcher";
import "./public-header.css";

export interface PublicHeaderProps {
  route: Route;
  onNav: (path: string) => void;
  locale: Locale;
  onSetLocale: (locale: Locale) => void;
  authOpen?: boolean;
  onAuthOpenChange?: (open: boolean) => void;
}

function routeMatchesNav(route: Route, href: string): boolean {
  const path = href.replace(/^#/, "") || "/";
  if (path === "/diseases") {
    return route.name === "diseaseIndex" || route.name === "disease";
  }
  if (path === "/doctors") {
    return route.name === "doctors" || route.name === "doctor";
  }
  if (path === "/start-research") {
    return route.name === "startResearch" || route.name === "researchRun";
  }
  if (path === "/about") {
    return route.name === "about";
  }
  return false;
}

function buildNavLinks(route: Route, t: TFunction): NavLink[] {
  // Mirrors the original draft2 layout: three primary links plus the brand
  // logo as the implicit "home" target. Trials live inside individual
  // disease detail views, not as a top-level destination.
  const base = [
    { href: "/doctors", label: t("nav.doctors") },
    { href: "/start-research", label: t("nav.startResearch") },
    { href: "/about", label: t("nav.about") },
  ];
  return base.map((link) => ({
    ...link,
    active: routeMatchesNav(route, link.href),
  }));
}

export function PublicHeader({
  route,
  onNav,
  locale,
  onSetLocale,
  authOpen: authOpenProp,
  onAuthOpenChange,
}: PublicHeaderProps) {
  const { t } = useTranslation("common");
  const { signInAvailable } = useAccountContext();
  const [account, setAccount] = useAccount();
  const [authOpenLocal, setAuthOpenLocal] = useState(false);
  const authOpen = authOpenProp ?? authOpenLocal;
  const setAuthOpen = onAuthOpenChange ?? setAuthOpenLocal;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  const onAuthSuccess = (acc: Account) => {
    setAccount(acc);
    setAuthOpen(false);
    onNav("/account");
  };

  // Auth0 mode (env-gated): the AccountMenu owns sign-in/out; the stub controls
  // below only run when no Auth0 tenant is configured.
  const mobileMenuActions = (
    <>
      <LocaleSwitcher locale={locale} onChange={onSetLocale} />
      {signInAvailable ? (
        <AccountMenu onNav={onNav} />
      ) : account != null ? (
        <>
          <button
            type="button"
            className="hdr-mobile-menu__btn"
            onClick={() => onNav("/account")}
          >
            {t("account.account")}
          </button>
          <button
            type="button"
            className="hdr-mobile-menu__btn"
            onClick={() => setAccount(null)}
          >
            {t("account.signOut")}
          </button>
        </>
      ) : (
        <button
          type="button"
          className="hdr-mobile-menu__btn hdr-mobile-menu__btn--primary"
          onClick={() => setAuthOpen(true)}
        >
          {t("account.signIn")}
        </button>
      )}
    </>
  );

  return (
    <>
      <AppHeader
        variant="public"
        navLinks={buildNavLinks(route, t)}
        mobileMenuContent={mobileMenuActions}
      >
        <div className="hdr-actions hdr-actions--desktop" ref={menuRef}>
          <LocaleSwitcher locale={locale} onChange={onSetLocale} />
          {signInAvailable ? (
            <AccountMenu onNav={onNav} />
          ) : account != null ? (
            <>
              <button
                type="button"
                className="hdr-actions__btn"
                onClick={() => setMenuOpen((o) => !o)}
                aria-expanded={menuOpen}
                aria-haspopup="menu"
              >
                {account.name}
              </button>
              {menuOpen ? (
                <div className="hdr-actions__menu" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onNav("/account");
                    }}
                  >
                    {t("account.account")}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setAccount(null);
                      setMenuOpen(false);
                    }}
                  >
                    {t("account.signOut")}
                  </button>
                </div>
              ) : null}
            </>
          ) : (
            <button
              type="button"
              className="hdr-actions__btn hdr-actions__btn--primary"
              onClick={() => setAuthOpen(true)}
            >
              {t("account.signIn")}
            </button>
          )}
        </div>
      </AppHeader>
      {!signInAvailable && authOpen ? (
        <AuthModal
          initialMode={account != null ? "login" : "register"}
          onClose={() => setAuthOpen(false)}
          onSuccess={onAuthSuccess}
        />
      ) : null}
    </>
  );
}
