import { useRef, useState, useEffect } from "react";
import { AppHeader, AuthModal, useAccount, type NavLink } from "@gene-guidelines/ui";
import type { Account } from "@gene-guidelines/ui";
import type { Route } from "../router/types";
import { AdminAppLink } from "./AdminAppLink";
import "./public-header.css";

export interface PublicHeaderProps {
  route: Route;
  onNav: (path: string) => void;
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
  if (path === "/add-disease") {
    return route.name === "addDisease";
  }
  if (path === "/start-research") {
    return route.name === "startResearch" || route.name === "researchRun";
  }
  if (path === "/about") {
    return route.name === "about";
  }
  return false;
}

function buildNavLinks(route: Route): NavLink[] {
  // Mirrors the original draft2 layout: three primary links plus the brand
  // logo as the implicit "home" target. Trials live inside individual
  // disease detail views, not as a top-level destination.
  const base = [
    { href: "#/doctors", label: "Doctors" },
    { href: "#/add-disease", label: "New research" },
    { href: "#/about", label: "About" },
  ];
  return base.map((link) => ({
    ...link,
    active: routeMatchesNav(route, link.href),
  }));
}

export function PublicHeader({
  route,
  onNav,
  authOpen: authOpenProp,
  onAuthOpenChange,
}: PublicHeaderProps) {
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

  return (
    <>
      <AppHeader variant="public" navLinks={buildNavLinks(route)}>
        <div className="hdr-actions" ref={menuRef}>
          <AdminAppLink />
          {account != null ? (
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
                    Account
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setAccount(null);
                      setMenuOpen(false);
                    }}
                  >
                    Sign out
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
              Sign in
            </button>
          )}
        </div>
      </AppHeader>
      {authOpen ? (
        <AuthModal
          initialMode={account != null ? "login" : "register"}
          onClose={() => setAuthOpen(false)}
          onSuccess={onAuthSuccess}
        />
      ) : null}
    </>
  );
}
