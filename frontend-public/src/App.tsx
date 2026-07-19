import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { userLocationFromCity } from "./config/cities";
import { useHistoryRouter } from "./router/useHistoryRouter";
import i18n from "./i18n";
import { useTweaks } from "./hooks/useTweaks";
import { JudgesBanner } from "./components/JudgesBanner";
import {
  JB_SESSION_FROM_KAGGLE_KEY,
  JB_STATE_KEY,
  judgesBannerRelevant,
} from "./components/judgesBannerState";
import { PublicHeader } from "./components/PublicHeader";
import { AppFooter } from "./components/AppFooter";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { TweaksPanel } from "./components/TweaksPanel";
import { routeContent } from "./views/routeContent";
import { AccountProvider } from "./auth/AccountProvider";
import { ViewAsProvider } from "./auth/ViewAsProvider";
import { useViewAsContext } from "./auth/viewAsContext";
import { useAccountContext } from "./auth/accountContext";
import { audienceForRole, resolveRole } from "./auth/resolveRole";
import { RolePickerModal } from "./auth/RolePickerModal";
import { getPendingInviteToken } from "./auth/pendingInvite";
import "./app.css";

const DevComponents = lazy(() => import("./pages/DevComponents"));

/**
 * Shows the one-time role picker after first login (Auth0 mode only). Suppressed
 * while an invite is pending — an invited doctor receives their role from the
 * invite accept flow (JoinView), not by self-selecting it here.
 */
function RolePickerGate() {
  const { needsRoleSelection, selectRole } = useAccountContext();
  if (!needsRoleSelection || getPendingInviteToken() != null) {
    return null;
  }
  return <RolePickerModal onSelect={selectRole} />;
}

export default function App() {
  return (
    <AccountProvider>
      <ViewAsProvider>
        <AppShell />
      </ViewAsProvider>
    </AccountProvider>
  );
}

function AppShell() {
  const { route, search, navigate, locale, setLocale } = useHistoryRouter();
  /* URL is the source of truth for locale: keep i18next and the document metadata
     in sync with the active URL prefix on every navigation. English is the default
     (unprefixed); Polish is the opt-in alternate under `/pl/`. */
  useEffect(() => {
    if (i18n.language !== locale) {
      void i18n.changeLanguage(locale);
    }
    document.documentElement.lang = locale;
    document
      .querySelector('meta[property="og:locale"]')
      ?.setAttribute("content", locale);
    try {
      localStorage.setItem("gg.locale", locale);
    } catch {
      /* storage blocked (private mode / disabled) — locale still lives in the URL */
    }
  }, [locale]);
  /* Judges arriving from the Kaggle submission link (?from=kaggle) get the
     full juror panel; everyone else gets the collapsed ribbon. */
  const fromKaggle = useMemo(
    () => new URLSearchParams(search).get("from") === "kaggle",
    [search],
  );
  /* The Kaggle juror banner is for judges only — render it for a ?from=kaggle arrival, a
     remembered Kaggle session, or a prior explicit interaction. A fresh family/clinician visitor
     never sees a hackathon ribbon on the public site. */
  const showJudgesBanner = useMemo(() => {
    let stored: string | null = null;
    let sessionFromKaggle = false;
    try {
      stored = localStorage.getItem(JB_STATE_KEY);
      sessionFromKaggle = sessionStorage.getItem(JB_SESSION_FROM_KAGGLE_KEY) === "1";
    } catch {
      /* storage blocked → treat as no prior context */
    }
    return judgesBannerRelevant({ stored, fromKaggle, sessionFromKaggle });
  }, [fromKaggle]);
  const { tweaks, setTweak } = useTweaks();
  const { account, isAuthenticated } = useAccountContext();
  const { viewAs } = useViewAsContext();
  const [authOpen, setAuthOpen] = useState(false);
  const userLoc = useMemo(
    () => userLocationFromCity(tweaks.userCity),
    [tweaks.userCity],
  );
  const role = resolveRole(account, tweaks.previewRole, isAuthenticated, viewAs);
  const view = audienceForRole(role);

  const main =
    route.name === "devComponents" ? (
      <Suspense fallback={<p className="page__loading">Loading…</p>}>
        <DevComponents />
      </Suspense>
    ) : (
      routeContent({
        route,
        view,
        role,
        userLoc,
        search,
        onNav: navigate,
        onSignIn: () => setAuthOpen(true),
      })
    );

  return (
    <div className="app-shell">
      {showJudgesBanner ? (
        <JudgesBanner route={route} onNav={navigate} fromKaggle={fromKaggle} />
      ) : null}
      <PublicHeader
        route={route}
        onNav={navigate}
        locale={locale}
        onSetLocale={setLocale}
        authOpen={authOpen}
        onAuthOpenChange={setAuthOpen}
      />
      <main className="app-main">
        <ErrorBoundary>{main}</ErrorBoundary>
      </main>
      <AppFooter onNav={navigate} />
      <RolePickerGate />
      {import.meta.env.DEV ? <TweaksPanel tweaks={tweaks} onTweak={setTweak} /> : null}
      {import.meta.env.DEV && route.name !== "devComponents" ? (
        <a className="dev-link" href="/dev/components">
          dev/components →
        </a>
      ) : null}
    </div>
  );
}
