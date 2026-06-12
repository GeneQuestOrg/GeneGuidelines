import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { userLocationFromCity } from "./config/cities";
import type { TweaksState } from "./hooks/useTweaks";
import { useHashRouter } from "./router/useHashRouter";
import { useTweaks } from "./hooks/useTweaks";
import { useAudienceView } from "./hooks/useAudienceView";
import { JudgesBanner } from "./components/JudgesBanner";
import { PublicHeader } from "./components/PublicHeader";
import { AppFooter } from "./components/AppFooter";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { TweaksPanel } from "./components/TweaksPanel";
import { routeContent } from "./views/routeContent";
import { AccountProvider } from "./auth/AccountProvider";
import { useAccountContext } from "./auth/accountContext";
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
      <AppShell />
    </AccountProvider>
  );
}

function AppShell() {
  const { route, navigate } = useHashRouter();
  const { tweaks, setTweak: setTweakBase } = useTweaks();
  const { view, setView } = useAudienceView(tweaks.defaultView);
  const [authOpen, setAuthOpen] = useState(false);
  const userLoc = useMemo(
    () => userLocationFromCity(tweaks.userCity),
    [tweaks.userCity],
  );

  const setTweak = useCallback(
    <K extends keyof TweaksState>(key: K, value: TweaksState[K]) => {
      setTweakBase(key, value);
      if (key === "defaultView") {
        setView(value as TweaksState["defaultView"]);
      }
    },
    [setTweakBase, setView],
  );

  const main =
    route.name === "devComponents" ? (
      <Suspense fallback={<p className="page__loading">Loading…</p>}>
        <DevComponents />
      </Suspense>
    ) : (
      routeContent({
        route,
        view,
        userLoc,
        onViewChange: setView,
        onNav: navigate,
        onSignIn: () => setAuthOpen(true),
      })
    );

  return (
    <div className="app-shell">
      <JudgesBanner route={route} onNav={navigate} />
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
