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

function GeneMarkSvg() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
      <path
        d="M5 4 C 5 14, 19 10, 19 20 M19 4 C 19 14, 5 10, 5 20"
        stroke="currentColor"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="8" cy="7" r="1" fill="currentColor" />
      <circle cx="16" cy="7" r="1" fill="currentColor" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
      <circle cx="8" cy="17" r="1" fill="currentColor" />
      <circle cx="16" cy="17" r="1" fill="currentColor" />
    </svg>
  );
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
            <GeneMarkSvg />
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
