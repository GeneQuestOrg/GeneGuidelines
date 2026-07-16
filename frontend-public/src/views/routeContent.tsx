import type { ReactNode } from "react";
import type { AudienceView, Route, UserLocation } from "../router/types";
import type { ViewRole } from "../auth/resolveRole";
import { HomeView } from "./HomeView";
import { DiseaseView } from "./DiseaseView";
import { DiseaseMapView } from "./DiseaseMapView";
import { DiseaseIndexView } from "./DiseaseIndexView";
import { PlaceholderView } from "./PlaceholderView";
import { AboutView } from "./AboutView";
import { BibliographyView } from "./BibliographyView";
import { GuidelinesView } from "./GuidelinesView";
import { FlowchartView } from "./FlowchartView";
import { DoctorsView } from "./DoctorsView";
import { DoctorProfileView } from "./DoctorProfileView";
import { AccountView } from "./AccountView";
import { JoinView } from "./JoinView";
import { ResearchRunView } from "./ResearchRunView";
import { StartResearchView } from "./StartResearchView";
import { MyCaseView } from "./MyCaseView";
import { TrialsBrowserView } from "./TrialsBrowserView";

export interface RouteContentProps {
  route: Route;
  view: AudienceView;
  role: ViewRole;
  userLoc: UserLocation | null;
  /** Current `location.search` — passed to views (e.g. the doctors directory) that own URL-synced query state. */
  search: string;
  onNav: (path: string) => void;
  onSignIn: () => void;
}

export function routeContent({
  route,
  view,
  role,
  userLoc,
  search,
  onNav,
  onSignIn,
}: RouteContentProps): ReactNode {
  switch (route.name) {
    case "home":
      return <HomeView view={view} onNav={onNav} />;
    case "disease":
      return (
        <DiseaseView
          slug={route.slug}
          role={role}
          userLoc={userLoc}
          onNav={onNav}
          alert={route.alert}
        />
      );
    case "myCase":
      return <MyCaseView slug={route.slug} onNav={onNav} />;
    case "diseaseMap":
      return <DiseaseMapView slug={route.slug} onNav={onNav} />;
    case "diseaseIndex":
      return <DiseaseIndexView initialQuery={route.query} onNav={onNav} />;
    case "account":
      return <AccountView onNav={onNav} onSignIn={onSignIn} />;
    case "join":
      return <JoinView token={route.token} onNav={onNav} />;
    case "about":
      return <AboutView view={view} onNav={onNav} />;
    case "doctors":
      return (
        <DoctorsView
          userLoc={userLoc}
          search={search}
          onNav={onNav}
        />
      );
    case "doctor":
      return (
        // key forces a clean remount per profile — local-rec state reads storage on mount
        <DoctorProfileView key={route.slug} slug={route.slug} userLoc={userLoc} onNav={onNav} />
      );
    case "startResearch":
      return (
        <StartResearchView
          key={route.diseaseSlug ?? "__none__"}
          initialDiseaseSlug={route.diseaseSlug}
          onNav={onNav}
        />
      );
    case "trials":
      return <TrialsBrowserView userLoc={userLoc} search={search} onNav={onNav} />;
    case "flowchart":
      return <FlowchartView slug={route.slug} onNav={onNav} />;
    case "bibliography":
      return (
        <BibliographyView slug={route.slug} role={role} onNav={onNav} />
      );
    case "guidelines":
      return (
        <GuidelinesView
          slug={route.slug}
          prId={route.prId}
          srcParaId={route.srcParaId}
          role={role}
          onNav={onNav}
        />
      );
    case "researchRun":
      return (
        <ResearchRunView
          executionId={route.id}
          diseaseSlug={route.diseaseSlug}
          diseaseName={route.diseaseName}
          queryTag={route.query}
          onNav={onNav}
        />
      );
    default:
      return (
        <PlaceholderView
          title="Page not found"
          description="This route is not implemented yet. Use the header to navigate home."
          primaryAction={{ label: "Home", path: "/" }}
          onNav={onNav}
        />
      );
  }
}
