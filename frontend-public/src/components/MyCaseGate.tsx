import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { MyCaseGateVariant } from "../auth/canAccessMyCaseUpload";
import "../styles/my-case.css";

export interface MyCaseGateProps {
  disease: Disease;
  variant: MyCaseGateVariant;
  onLogin: () => void;
}

const PROMISE_KEYS: readonly string[] = [
  "promise0",
  "promise1",
  "promise2",
  "promise3",
  "promise4",
];

export function MyCaseGate({ disease, variant, onLogin }: MyCaseGateProps) {
  const { t } = useTranslation("my-case");
  const subtitle =
    variant === "needs-role"
      ? t("gateSubtitleNeedsRole")
      : variant === "wrong-role"
        ? t("gateSubtitleWrongRole")
        : t("gateSubtitleSignIn");

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

      <h1 className="mycase__gate-title">{t("gateTitle")}</h1>
      <p className="mycase__gate-lede">{subtitle}</p>

      {variant === "sign-in" ? (
        <>
          <p className="mycase__gate-intro">
            {t("gateIntroBefore")} <b>{disease.name}</b>
            {t("gateIntroAfter")}
          </p>
          <ul className="mycase__gate-promises">
            {PROMISE_KEYS.map((key, index) => (
              <li key={index}>
                <span className="mycase__chk" aria-hidden>
                  ✓
                </span>
                <span>
                  {index === 3 ? (
                    <>
                      {t("promise3For")} <b>{disease.nameShort}</b>
                    </>
                  ) : (
                    t(key)
                  )}
                </span>
              </li>
            ))}
          </ul>

          <div className="mycase__gate-coming">
            <p className="mycase__gate-coming-label">{t("comingSoonLabel")}</p>
            <ul className="mycase__gate-coming-list">
              <li>{t("comingSoon1")}</li>
              <li>{t("comingSoon2")}</li>
              <li>{t("comingSoon3")}</li>
            </ul>
          </div>
        </>
      ) : null}

      <div className="mycase__gate-actions">
        {variant === "sign-in" ? (
          <>
            <Button variant="primary" size="lg" type="button" onClick={onLogin}>
              {t("createAccountButton")}
            </Button>
            <Button variant="ghost" size="lg" type="button" onClick={onLogin}>
              {t("signInButton")}
            </Button>
          </>
        ) : variant === "needs-role" ? (
          <p className="mycase__gate-hint" role="status">
            {t("gateHintBefore")} <b>{t("gateHintRole")}</b>
            {t("gateHintAfter")}
          </p>
        ) : (
          <Button variant="ghost" size="lg" type="button" onClick={onLogin}>
            {t("switchAccountButton")}
          </Button>
        )}
      </div>

      <p className="mycase__gate-foot">{t("gateFooter")}</p>
    </div>
  );
}
