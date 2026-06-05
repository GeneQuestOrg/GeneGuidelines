import { SignInButton, SignUpButton } from "@clerk/clerk-react";
import { Button } from "@gene-guidelines/ui";
import "../styles/research.css";

export interface ResearchSignInPromptProps {
  readonly title: string;
  readonly lead: string;
  readonly onNav: (path: string) => void;
}

/** Shown on research routes when Clerk is on and the visitor is signed out. */
export function ResearchSignInPrompt({ title, lead, onNav }: ResearchSignInPromptProps) {
  return (
    <section className="page page--research">
      <h1>{title}</h1>
      <p className="research__lead">{lead}</p>
      <p className="research__hint">
        Sign in or create a free account to continue. Your runs stay linked to your profile and
        count toward your quota.
      </p>
      <div className="research__actions">
        <SignInButton mode="modal">
          <Button variant="primary" type="button">
            Sign in
          </Button>
        </SignInButton>
        <SignUpButton mode="modal">
          <Button variant="ghost" type="button">
            Create account
          </Button>
        </SignUpButton>
        <Button type="button" onClick={() => onNav("/")}>
          Back to home
        </Button>
      </div>
    </section>
  );
}
