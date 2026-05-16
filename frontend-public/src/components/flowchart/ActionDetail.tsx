import type { PathwayActionNode } from "../../types/parentPathway";

export interface ActionDetailProps {
  action: PathwayActionNode;
}

export function ActionDetail({ action }: ActionDetailProps) {
  return (
    <div className={`action ${action.urgent ? "action--urgent" : ""}`}>
      {action.urgent ? (
        <div className="action__urgent">URGENT — contact your care team today</div>
      ) : null}
      <p className="action__lead">You chose this step — here is how to move forward.</p>
      <h2 className="action__title">{action.title}</h2>
      <div className="action__spec">
        <div className="action__label">Who can help</div>
        <div>{action.specialty}</div>
      </div>
      {action.whatToExpect ? (
        <div className="action__what">
          <div className="action__label">What to expect</div>
          <p>{action.whatToExpect}</p>
        </div>
      ) : null}
      {action.questions.length > 0 ? (
        <div className="action__qs">
          <div className="action__label">Questions to ask (you can read these aloud)</div>
          <ol>
            {action.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </div>
      ) : null}
      {action.evidenceGap ? (
        <p className="action__evidence-gap">
          Evidence for this step is limited in the current guideline — confirm with your care
          team.
        </p>
      ) : null}
    </div>
  );
}
