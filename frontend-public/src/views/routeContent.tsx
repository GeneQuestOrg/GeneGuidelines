import type { ReactNode } from "react";
import { RequireSignedIn } from "../auth/RequireSignedIn";
import { ResearchSignInPrompt } from "../auth/ResearchSignInPrompt";
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
      return <AccountView onNav={onNav} onSignIn={onSignIn} view={view} onViewChange={onViewChange} />;
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
        <DoctorProfileView slug={route.slug} userLoc={userLoc} onNav={onNav} />
      );
    case "startResearch":
      return (
        <RequireSignedIn
          fallback={
            <ResearchSignInPrompt
              title="Start research"
              lead="Sign in to launch a guideline research run for a catalog disease or a custom name."
              onNav={onNav}
            />
          }
        >
          <StartResearchView
            key={route.diseaseSlug ?? "__none__"}
            initialDiseaseSlug={route.diseaseSlug}
            onNav={onNav}
          />
        </RequireSignedIn>
      );
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
        <RequireSignedIn
          fallback={
            <ResearchSignInPrompt
              title="Research run"
              lead="Sign in to view live trace output and results for this research run."
              onNav={onNav}
            />
          }
        >
          <ResearchRunView
            executionId={route.id}
            diseaseSlug={route.diseaseSlug}
            diseaseName={route.diseaseName}
            queryTag={route.query}
            onNav={onNav}
          />
        </RequireSignedIn>
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
