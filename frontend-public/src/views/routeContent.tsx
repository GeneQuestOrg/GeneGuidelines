import type { ReactNode } from "react";
import type { AudienceView, Route, UserLocation } from "../router/types";
import type { ViewRole } from "../auth/resolveRole";
import { HomeView } from "./HomeView";
import { DiseaseView } from "./DiseaseView";
import { DiseaseIndexView } from "./DiseaseIndexView";
import { PlaceholderView } from "./PlaceholderView";
import { AboutView } from "./AboutView";
import { GuidelinesView } from "./GuidelinesView";
import { FlowchartView } from "./FlowchartView";
import { DoctorsView } from "./DoctorsView";
import { DoctorProfileView } from "./DoctorProfileView";
import { AccountView } from "./AccountView";
import { JoinView } from "./JoinView";
import { ResearchRunView } from "./ResearchRunView";
import { StartResearchView } from "./StartResearchView";
import { TrialsView } from "./TrialsView";

export interface RouteContentProps {
  route: Route;
  view: AudienceView;
  role: ViewRole;
  userLoc: UserLocation | null;
  onNav: (path: string) => void;
  onSignIn: () => void;
}

export function routeContent({
  route,
  view,
  role,
  userLoc,
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
        />
      );
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
          initialDisease={route.disease}
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
      return <TrialsView initialQuery={route.query} onNav={onNav} />;
    case "flowchart":
      return <FlowchartView slug={route.slug} onNav={onNav} />;
    case "guidelines":
      // prId (old PR-diff route) degrades to the synthesis view in GL-2;
      // FocusedReview lands in GL-3.
      return <GuidelinesView slug={route.slug} role={role} onNav={onNav} />;
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
