import { useEffect, useState, type ReactNode } from "react";
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
  mobileMenuContent?: ReactNode;
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

export function AppHeader({
  variant = "public",
  navLinks,
  children,
  mobileMenuContent,
}: AppHeaderProps) {
  const isAdmin = variant === "admin";
  const links = navLinks ?? (isAdmin ? DEFAULT_ADMIN_LINKS : DEFAULT_PUBLIC_LINKS);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth > 900) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <header className="hdr">
      <div className="hdr__row">
        <a href="#/" className="hdr__brand">
          <span className="hdr__mark">
            <img src="/logo.png" alt="" />
          </span>
          <span className="hdr__name">GeneGuidelines</span>
          <span className="hdr__by">{isAdmin ? "/ Admin" : "/ GeneQuest"}</span>
        </a>
        <button
          type="button"
          className="hdr__menu-toggle"
          aria-expanded={menuOpen}
          aria-controls="main-navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          Menu
        </button>
        <nav
          id="main-navigation"
          className={menuOpen ? "hdr__nav is-open" : "hdr__nav"}
          aria-label="Main navigation"
          onClick={(event) => {
            const target = event.target as HTMLElement | null;
            if (target?.closest("a,button") != null) {
              setMenuOpen(false);
            }
          }}
        >
          {links.map((link) => (
            <a
              key={link.href}
              href={safeBrandHref(link.href, "#/")}
              className={link.active === true ? "is-active" : undefined}
            >
              {link.label}
            </a>
          ))}
          {mobileMenuContent != null ? (
            <div className="hdr__nav-mobile-content">{mobileMenuContent}</div>
          ) : null}
        </nav>
        {children != null ? children : null}
      </div>
    </header>
  );
}
