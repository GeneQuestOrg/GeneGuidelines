import { useTranslation } from "react-i18next";
import { Button, Section } from "@gene-guidelines/ui";
import type { ParentOrientationCopy } from "../copy/types";
import type { SourceDoc } from "../types/sourceDoc";
import { citationLine, familyDoctorMailto } from "../utils/familyDoctorMail";
import { printOnly } from "../utils/printOnly";
import { CompactSourceShelf } from "./guidelines/CompactSourceShelf";
import "../styles/family-doctor.css";

/** Set on `<html>` while the page prints only this list (see family-doctor.css). */
export const PRINT_FAMILY_DOCTOR_CLASS = "print-family-doctor";

export interface FamilyDoctorMaterialsProps {
  readonly docs: readonly SourceDoc[];
  readonly copy: ParentOrientationCopy;
  readonly diseaseName: string;
  readonly onSeeAll: () => void;
}

/**
 * "Materials for the family doctor": the disease's source shelf, which a parent can print or e-mail to a doctor who has never seen the disease. Print puts only this list on paper, with every address written out, because a link cannot be clicked on paper; the rest of the page stays on screen. E-mail opens the parent's own mail program with the same list.
 */
export function FamilyDoctorMaterials({ docs, copy, diseaseName, onSeeAll }: FamilyDoctorMaterialsProps) {
  const { t } = useTranslation("parent");
  if (docs.length === 0) {
    return null;
  }
  const etAl = t("orientation.etAl");
  const mailto = familyDoctorMailto(
    docs,
    t("orientation.emailForDoctorSubject", { name: diseaseName }),
    t("orientation.emailForDoctorIntro", { name: diseaseName }),
    etAl,
  );

  return (
    <div className="fdoc">
      <Section
        title={copy.familyDoctorTitle}
        sub={copy.familyDoctorSub}
        action={
          <div className="fdoc__actions">
            <Button type="button" variant="ghost" onClick={() => printOnly(PRINT_FAMILY_DOCTOR_CLASS)}>
              {t("orientation.printForDoctorCta")}
            </Button>
            <Button as="a" variant="ghost" href={mailto}>
              {t("orientation.emailForDoctorCta")}
            </Button>
          </div>
        }
        divider
      >
        <CompactSourceShelf docs={docs} onSeeAll={onSeeAll} />
        <ol className="fdoc-print">
          {docs.map((doc) => (
            <li key={doc.id}>
              <span className="fdoc-print__role">{doc.role}</span>
              {citationLine(doc, etAl)}
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
