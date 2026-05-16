import type { PathwayActionNode } from "../../types/parentPathway";

export interface PathwayActionDetailProps {
  action: PathwayActionNode;
}

export function PathwayActionDetail({ action }: PathwayActionDetailProps) {
  return (
    <div className={`ops-pp-action ${action.urgent ? "ops-pp-action--urgent" : ""}`}>
      {action.urgent ? (
        <p className="ops-pp-action__urgent">URGENT — seek a specialist within 24–48 hours</p>
      ) : null}
      <h4 className="ops-pp-action__title">{action.title}</h4>
      <div className="ops-pp-action__block">
        <div className="ops-pp-action__label">Specialist</div>
        <p>{action.specialty}</p>
      </div>
      {action.whatToExpect ? (
        <div className="ops-pp-action__block">
          <div className="ops-pp-action__label">What to expect</div>
          <p>{action.whatToExpect}</p>
        </div>
      ) : null}
      {action.questions.length > 0 ? (
        <div className="ops-pp-action__block">
          <div className="ops-pp-action__label">Questions to ask</div>
          <ol>
            {action.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
