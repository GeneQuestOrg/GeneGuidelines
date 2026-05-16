import type { ReactNode } from "react";
import { safeBrandHref } from "./safeBrandHref";
import "./app-header.css";

export type AppHeaderVariant = "public" | "admin";

export interface NavLink {
  href: string;
  label: string;
  active?: boolean;
}

export interface AppHeaderProps {
  variant?: AppHeaderVariant;
  navLinks?: NavLink[];
  children?: ReactNode;
}

const DEFAULT_PUBLIC_LINKS: NavLink[] = [
  { href: "#/diseases", label: "Diseases" },
  { href: "#/doctors", label: "Doctors" },
  { href: "#/about", label: "About" },
];

const DEFAULT_ADMIN_LINKS: NavLink[] = [
  { href: "#/runs", label: "Runs" },
  { href: "#/guidelines", label: "Guidelines" },
  { href: "#/tools", label: "Tools" },
];

export function AppHeader({ variant = "public", navLinks, children }: AppHeaderProps) {
  const isAdmin = variant === "admin";
  const links = navLinks ?? (isAdmin ? DEFAULT_ADMIN_LINKS : DEFAULT_PUBLIC_LINKS);

  return (
    <header className="hdr">
      <div className="hdr__row">
        <a href="#/" className="hdr__brand">
          <span className="hdr__mark">
            <img src="/logo.png" alt="" width="24" height="24" />
          </span>
          <span className="hdr__name">GeneGuidelines</span>
          <span className="hdr__by">{isAdmin ? "/ Admin" : "/ GeneQuest"}</span>
        </a>
        <nav className="hdr__nav" aria-label="Main navigation">
          {links.map((link) => (
            <a
              key={link.href}
              href={safeBrandHref(link.href, "#/")}
              className={link.active === true ? "is-active" : undefined}
            >
              {link.label}
            </a>
          ))}
        </nav>
        {children != null ? children : null}
      </div>
    </header>
  );
}
