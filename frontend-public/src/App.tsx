import { lazy, Suspense, useMemo, useState } from "react";
import { userLocationFromCity } from "./config/cities";
import { useHashRouter } from "./router/useHashRouter";
import { useTweaks } from "./hooks/useTweaks";
import { JudgesBanner } from "./components/JudgesBanner";
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
  const { route, hash, navigate } = useHashRouter();
  /* Judges arriving from the Kaggle submission link (?from=kaggle) get the
     full juror panel; everyone else gets the collapsed ribbon. */
  const fromKaggle = useMemo(() => {
    const queryStart = hash.indexOf("?");
    if (queryStart === -1) {
      return false;
    }
    return new URLSearchParams(hash.slice(queryStart + 1)).get("from") === "kaggle";
  }, [hash]);
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
        hash,
        onNav: navigate,
        onSignIn: () => setAuthOpen(true),
      })
    );

  return (
    <div className="app-shell">
      <JudgesBanner route={route} onNav={navigate} fromKaggle={fromKaggle} />
      <PublicHeader
        route={route}
        onNav={navigate}
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
        <a className="dev-link" href="#/dev/components">
          dev/components →
        </a>
      ) : null}
    </div>
  );
}
