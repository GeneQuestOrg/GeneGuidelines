import { useTranslation } from "react-i18next";
import type { PathwayActionNode } from "../../types/parentPathway";

export interface ActionDetailProps {
  action: PathwayActionNode;
}

export function ActionDetail({ action }: ActionDetailProps) {
  const { t } = useTranslation("misc");
  return (
    <div className={`action ${action.urgent ? "action--urgent" : ""}`}>
      {action.urgent ? (
        <div className="action__urgent">{t("flowchart.actionUrgent")}</div>
      ) : null}
      <p className="action__lead">{t("flowchart.actionLead")}</p>
      <h2 className="action__title">{action.title}</h2>
      <div className="action__spec">
        <div className="action__label">{t("flowchart.actionWhoLabel")}</div>
        <div>{action.specialty}</div>
      </div>
      {action.whatToExpect ? (
        <div className="action__what">
          <div className="action__label">{t("flowchart.actionWhatLabel")}</div>
          <p>{action.whatToExpect}</p>
        </div>
      ) : null}
      {action.questions.length > 0 ? (
        <div className="action__qs">
          <div className="action__label">{t("flowchart.actionQuestionsLabel")}</div>
          <ol>
            {action.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </div>
      ) : null}
      {action.evidenceGap ? (
        <p className="action__evidence-gap">{t("flowchart.actionEvidenceGap")}</p>
      ) : null}
    </div>
  );
}
