import { useTranslation } from "react-i18next";
import "./app-footer.css";

export interface AppFooterProps {
  onNav: (path: string) => void;
}

export function AppFooter({ onNav }: AppFooterProps) {
  const { t } = useTranslation("common");
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
        <div className="site-footer__brand">{t("footer.brand")}</div>
        <p className="site-footer__desc">{t("footer.desc")}</p>
        <p className="site-footer__desc">
          {t("footer.poweredByLead")}
          <strong>{t("footer.poweredByModel")}</strong>
          {t("footer.poweredByTail")}
        </p>
      </div>
      <nav className="site-footer__links" aria-label={t("footer.navLabel")}>
        {link("/", t("footer.home"))}
        {link("/start-research", t("footer.startResearch"))}
        {link("/about", t("footer.about"))}
        {link("/account", t("footer.account"))}
      </nav>
    </footer>
  );
}
