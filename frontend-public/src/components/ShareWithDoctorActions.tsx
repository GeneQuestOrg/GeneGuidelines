import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";
import {
  buildEmailShareUrl,
  buildWhatsAppShareUrl,
  getCurrentPageUrl,
} from "../utils/sharePage";
import { trackEvent } from "../utils/analytics";

export interface ShareWithDoctorActionsProps {
  diseaseName: string;
}

/**
 * Share the current guideline page with a doctor — copy link, WhatsApp, or
 * email. Client-side only: every action carries the page URL / opens a share
 * target; nothing is sent to our backend and no medical claim is made.
 */
export function ShareWithDoctorActions({ diseaseName }: ShareWithDoctorActionsProps) {
  const { t } = useTranslation("guidelines");
  const [copied, setCopied] = useState(false);

  const url = getCurrentPageUrl();
  const whatsappHref = buildWhatsAppShareUrl(
    t("shareMessage", { disease: diseaseName, url }),
  );
  const emailHref = buildEmailShareUrl(
    t("shareEmailSubject", { disease: diseaseName }),
    t("shareEmailBody", { url }),
  );

  const copyLink = () => {
    trackEvent("share-disease-link", { method: "copy" });
    void navigator.clipboard?.writeText(url).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      },
      () => setCopied(false),
    );
  };

  return (
    <div className="gx-send__share" role="group" aria-label={t("sendDoctorButton")}>
      <Button
        variant="primary"
        size="sm"
        type="button"
        onClick={copyLink}
        aria-label={copied ? t("shareCopiedAria") : t("shareCopyAria")}
      >
        {copied ? t("shareCopied") : t("shareCopyLink")}
      </Button>
      <Button
        as="a"
        size="sm"
        href={whatsappHref}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => trackEvent("share-disease-link", { method: "whatsapp" })}
      >
        {t("shareWhatsApp")}
      </Button>
      <Button
        as="a"
        size="sm"
        href={emailHref}
        onClick={() => trackEvent("share-disease-link", { method: "email" })}
      >
        {t("shareEmail")}
      </Button>
    </div>
  );
}
