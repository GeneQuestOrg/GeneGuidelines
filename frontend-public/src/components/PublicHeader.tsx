import { useEffect } from "react";
import { AppHeader, type NavLink } from "@gene-guidelines/ui";
import type { Route } from "../router/types";
import { HeaderAuthActions } from "../auth/HeaderAuthActions";
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
  if (path === "/start-research") {
    return route.name === "startResearch" || route.name === "researchRun";
  }
  if (path === "/about") {
    return route.name === "about";
  }
  return false;
}

function buildNavLinks(route: Route): NavLink[] {
  const base = [
    { href: "#/doctors", label: "Doctors" },
    { href: "#/start-research", label: "New research" },
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
  authOpen,
  onAuthOpenChange,
}: PublicHeaderProps) {
  useEffect(() => {
    if (!authOpen) return;
    onAuthOpenChange?.(false);
    onNav("/account");
  }, [authOpen, onAuthOpenChange, onNav]);

  return (
    <AppHeader variant="public" navLinks={buildNavLinks(route)}>
      <div className="hdr-actions">
        <AdminAppLink />
        <HeaderAuthActions onNav={onNav} />
      </div>
    </AppHeader>
  );
}
