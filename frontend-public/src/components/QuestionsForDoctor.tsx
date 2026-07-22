import { useState } from "react";
import { useTranslation } from "react-i18next";
import "../styles/disease-page.css";

export interface QuestionsForDoctorProps {
  questions: readonly string[];
}

/**
 * Plain, copy-paste "Questions for the doctor" block (Phase 3, draft11 spine).
 * Each question is selectable text; "Copy all" puts the list on the clipboard
 * so a family can paste it into notes or a message.
 */
export function QuestionsForDoctor({ questions }: QuestionsForDoctorProps) {
  const { t } = useTranslation("common");
  const [copied, setCopied] = useState(false);

  const copyAll = () => {
    const text = questions.map((q) => `- ${q}`).join("\n");
    void navigator.clipboard?.writeText(text).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      },
      () => setCopied(false),
    );
  };

  return (
    <div className="qfd">
      <ul className="qfd__list">
        {questions.map((q) => (
          <li key={q}>{q}</li>
        ))}
      </ul>
      <button type="button" className="qfd__copy" onClick={copyAll}>
        {copied ? t("questionsForDoctor.copied") : t("questionsForDoctor.copyAll")}
      </button>
    </div>
  );
}
