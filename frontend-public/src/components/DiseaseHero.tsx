import { useTranslation } from "react-i18next";
import { Button, Status } from "@gene-guidelines/ui";
import type { Disease } from "../types";
import type { DiseaseCopy } from "../copy";
import type { SubscriptionUiStatus } from "../utils/diseaseSubscriptionStorage";
import "../styles/disease-page.css";

export interface DiseaseHeroProps {
  disease: Disease;
  copy: DiseaseCopy;
  isClinician: boolean;
  subscriptionStatus: SubscriptionUiStatus;
  onNav: (path: string) => void;
  onSubscribe: () => void;
}

export function DiseaseHero({
  disease,
  copy,
  isClinician,
  subscriptionStatus,
  onNav,
  onSubscribe,
}: DiseaseHeroProps) {
  const { t } = useTranslation("common");
  const slug = disease.slug;
  // The "pending" status carries the safety-critical epistemic frame ("AI-drafted…,
  // not an official guideline"). Localize it so a Polish reader sees Polish framing;
  // other statuses keep the shared-UI English defaults for now.
  const statusOverride =
    disease.status === "pending"
      ? { label: t("status.pending.label"), text: t("status.pending.text") }
      : {};
  const notifyLabel =
    subscriptionStatus === "confirmed"
      ? copy.notifySubscribedCta
      : subscriptionStatus === "pending"
        ? copy.notifyPendingCta
        : copy.notifyCta;

  return (
    <div className={`d-hero d-hero--${disease.accent}`}>
      <div className="d-hero__top">
        <div className="d-hero__abbr">{disease.nameShort}</div>
        <div className="d-hero__title-block">
          <h1 className="d-hero__name">{disease.name}</h1>
        </div>
        <Status status={disease.status} {...statusOverride} />
      </div>
      <p className="d-hero__summary">{disease.summary}</p>
      <dl className="d-hero__facts">
        <div>
          <dt>{t("diseaseFacts.gene")}</dt>
          <dd>
            <code>{disease.gene}</code>
          </dd>
        </div>
        <div>
          <dt>{t("diseaseFacts.omim")}</dt>
          <dd>
            <code>{disease.omim}</code>
          </dd>
        </div>
        <div>
          <dt>{t("diseaseFacts.inheritance")}</dt>
          <dd>{disease.inheritance}</dd>
        </div>
        <div>
          <dt>{t("diseaseFacts.prevalence")}</dt>
          <dd>{disease.prevalenceText}</dd>
        </div>
        <div>
          <dt>{t("diseaseFacts.types")}</dt>
          <dd>{disease.types.join(" · ")}</dd>
        </div>
        {(disease.statusDate ?? disease.aiDraftDate) != null ? (
          <div>
            <dt>{t("diseaseFacts.lastRevised")}</dt>
            <dd>{disease.statusDate ?? disease.aiDraftDate}</dd>
          </div>
        ) : null}
      </dl>
      {disease.coverage === "skeleton" ? (
        <div className="d-hero__notice" role="note">
          <span aria-hidden>⚠️</span>
          <p>
            <b>{copy.skeletonNoticeTitle}</b> {copy.skeletonNoticeBody}
          </p>
        </div>
      ) : null}
      <div className="d-hero__actions">
        {isClinician ? (
          <Button
            variant="primary"
            type="button"
            onClick={() => onNav(`/diseases/${slug}/guidelines`)}
          >
            {copy.guidelinesCta}
          </Button>
        ) : (
          <Button
            variant="primary"
            type="button"
            onClick={() => onNav(`/diseases/${slug}/my-case`)}
          >
            {copy.myCaseCta}
          </Button>
        )}
        <Button
          type="button"
          variant={subscriptionStatus === "confirmed" ? "ghost" : "default"}
          onClick={onSubscribe}
        >
          {notifyLabel}
        </Button>
        <Button type="button" onClick={() => onNav(`/diseases/${slug}/guidelines`)}>
          {copy.synthesisCta}
        </Button>
      </div>
    </div>
  );
}
