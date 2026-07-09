import { useState } from "react";
import { Button } from "@gene-guidelines/ui";
import {
  buildEmailShareUrl,
  buildWhatsAppShareUrl,
  getCurrentPageUrl,
  shareMessage,
} from "../utils/sharePage";

export interface ShareWithDoctorActionsProps {
  diseaseName: string;
}

/**
 * Share the current guideline page with a doctor — copy link, WhatsApp, or email.
 */
export function ShareWithDoctorActions({ diseaseName }: ShareWithDoctorActionsProps) {
  const [copied, setCopied] = useState(false);
  const url = getCurrentPageUrl();
  const message = shareMessage(diseaseName, url);
  const whatsappHref = buildWhatsAppShareUrl(message);
  const emailHref = buildEmailShareUrl(
    `Guideline summary: ${diseaseName}`,
    `Hello,\n\nI wanted to share this guideline summary with you:\n\n${url}\n\nThank you.`,
  );

  const copyLink = () => {
    void navigator.clipboard?.writeText(url).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      },
      () => setCopied(false),
    );
  };

  return (
    <div className="gx-send__share" role="group" aria-label="Send to doctor">
      <Button
        variant="primary"
        size="sm"
        type="button"
        onClick={copyLink}
        aria-label={copied ? "Link copied" : "Copy link to clipboard"}
      >
        {copied ? "Copied" : "Copy link"}
      </Button>
      <Button
        as="a"
        size="sm"
        href={whatsappHref}
        target="_blank"
        rel="noopener noreferrer"
      >
        WhatsApp
      </Button>
      <Button as="a" size="sm" href={emailHref}>
        Email
      </Button>
    </div>
  );
}
