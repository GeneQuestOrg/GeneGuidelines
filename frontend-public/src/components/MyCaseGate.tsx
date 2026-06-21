import { Button } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { MyCaseGateVariant } from "../auth/canAccessMyCaseUpload";
import "../styles/my-case.css";

export interface MyCaseGateProps {
  disease: Disease;
  variant: MyCaseGateVariant;
  onLogin: () => void;
}

const PROMISES: readonly string[] = [
  "Keep discharge summaries and lab results in one private place — ready to share with specialists when you choose",
  "Gemma 4 strips personal identifiers (names, IDs, exact dates, addresses) before anything is saved",
  "Only anonymized clinical facts persist — the original is processed in memory and never stored on disk",
  "Anonymized facts help AI analyze patterns and speed research on new treatments and sharper diagnostics",
  "You stay in control: facts are private to your account; sharing with verified clinicians is opt-in",
];

export function MyCaseGate({ disease, variant, onLogin }: MyCaseGateProps) {
  const subtitle =
    variant === "needs-role"
      ? "Choose the patient / caregiver role to unlock your private upload zone."
      : variant === "wrong-role"
        ? "My case is for patient and caregiver accounts. Clinician accounts can browse guidelines and suggest doctors elsewhere."
        : "Upload your results to share them conveniently with specialists. By contributing an anonymized version for AI analysis, you directly support research on new treatments and more precise diagnostics.";

  return (
    <div className="mycase__gate">
      <div className="mycase__gate-icon" aria-hidden>
        <svg
          width="56"
          height="56"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      </div>

      <h1 className="mycase__gate-title">My case — private zone</h1>
      <p className="mycase__gate-lede">{subtitle}</p>

      {variant === "sign-in" ? (
        <>
          <p className="mycase__gate-intro">
            For <b>{disease.name}</b>, your records are a rare clinical signal — useful for your care
            team and for building better evidence for similar families.
          </p>
          <ul className="mycase__gate-promises">
            {PROMISES.map((text, index) => (
              <li key={index}>
                <span className="mycase__chk" aria-hidden>
                  ✓
                </span>
                <span>
                  {index === 3 ? (
                    <>
                      Anonymized facts help AI analyze patterns and speed research on new treatments
                      and sharper diagnostics for <b>{disease.nameShort}</b>
                    </>
                  ) : (
                    text
                  )}
                </span>
              </li>
            ))}
          </ul>

          <div className="mycase__gate-coming">
            <p className="mycase__gate-coming-label">Coming soon with your account</p>
            <ul className="mycase__gate-coming-list">
              <li>Custom research runs tuned to your mutation and phenotype</li>
              <li>Trial alerts when a study matches your case</li>
              <li>Optional sharing with verified clinicians — off by default</li>
            </ul>
          </div>
        </>
      ) : null}

      <div className="mycase__gate-actions">
        {variant === "sign-in" ? (
          <>
            <Button variant="primary" size="lg" type="button" onClick={onLogin}>
              Create parent / caregiver account
            </Button>
            <Button variant="ghost" size="lg" type="button" onClick={onLogin}>
              Sign in
            </Button>
          </>
        ) : variant === "needs-role" ? (
          <p className="mycase__gate-hint" role="status">
            Use the role picker to continue — choose <b>Patient / caregiver</b>.
          </p>
        ) : (
          <Button variant="ghost" size="lg" type="button" onClick={onLogin}>
            Switch account
          </Button>
        )}
      </div>

      <p className="mycase__gate-foot">
        Guidelines, doctors, and trials on GeneGuidelines stay available without an account.
      </p>
    </div>
  );
}
