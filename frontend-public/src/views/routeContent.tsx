import type { ReactNode } from "react";
import type { AudienceView, Route, UserLocation } from "../router/types";
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
import { ResearchRunView } from "./ResearchRunView";
import { StartResearchView } from "./StartResearchView";
import { AddDiseaseView } from "./AddDiseaseView";
import { TrialsView } from "./TrialsView";

export interface RouteContentProps {
  route: Route;
  view: AudienceView;
  userLoc: UserLocation | null;
  onViewChange: (v: AudienceView) => void;
  onNav: (path: string) => void;
  onSignIn: () => void;
}

export function routeContent({
  route,
  view,
  userLoc,
  onViewChange,
  onNav,
  onSignIn,
}: RouteContentProps): ReactNode {
  switch (route.name) {
    case "home":
      return <HomeView view={view} onViewChange={onViewChange} onNav={onNav} />;
    case "disease":
      return (
        <DiseaseView
          slug={route.slug}
          view={view}
          userLoc={userLoc}
          onViewChange={onViewChange}
          onNav={onNav}
        />
      );
    case "diseaseIndex":
      return <DiseaseIndexView initialQuery={route.query} onNav={onNav} />;
    case "account":
      return <AccountView onNav={onNav} onSignIn={onSignIn} />;
    case "about":
      return <AboutView view={view} onViewChange={onViewChange} onNav={onNav} />;
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
        <DoctorProfileView slug={route.slug} userLoc={userLoc} onNav={onNav} />
      );
    case "startResearch":
      return (
        <StartResearchView
          key={route.diseaseSlug ?? "__none__"}
          initialDiseaseSlug={route.diseaseSlug}
          onNav={onNav}
        />
      );
    case "addDisease":
      return <AddDiseaseView onNav={onNav} />;
    case "trials":
      return <TrialsView initialQuery={route.query} onNav={onNav} />;
    case "flowchart":
      return <FlowchartView slug={route.slug} onNav={onNav} />;
    case "guidelines":
      return (
        <GuidelinesView
          slug={route.slug}
          prId={route.prId}
          view={view}
          onNav={onNav}
        />
      );
    case "researchRun":
      return (
        <ResearchRunView
          executionId={route.id}
          diseaseSlug={route.diseaseSlug}
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
