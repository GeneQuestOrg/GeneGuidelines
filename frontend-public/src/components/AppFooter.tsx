import "./app-footer.css";

export interface AppFooterProps {
  onNav: (path: string) => void;
}

export function AppFooter({ onNav }: AppFooterProps) {
  const link = (path: string, label: string) => (
    <a
      href={path}
      onClick={(e) => {
        e.preventDefault();
        onNav(path);
      }}
    >
      {label}
    </a>
  );

  return (
    <footer className="site-footer">
      <div>
        <div className="site-footer__brand">GeneQuest Foundation</div>
        <p className="site-footer__desc">
          Living guidelines for rare genetic diseases — AI-drafted updates, reviewed by
          specialists, refreshed on demand.
        </p>
        <p className="site-footer__desc">
          Powered by <strong>Gemma 4</strong> — an open model that can run on-device, so a
          family&apos;s documents are de-identified before anything leaves the building.
        </p>
      </div>
      <nav className="site-footer__links" aria-label="Footer">
        {link("/", "Home")}
        {link("/start-research", "Start research")}
        {link("/about", "About the project")}
        {link("/account", "Your account")}
      </nav>
    </footer>
  );
}
