import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { AudienceView } from "../router/types";
import { buildDiseaseCopy, buildHomeCopy } from "./build";
import type { AudienceCopy } from "./types";

/**
 * Audience-keyed copy, bridged to i18next. The homepage copy is audience-agnostic
 * (one `home` namespace shared by both audiences); the disease-page chrome lives in
 * the audience namespace (`parent` / `doctor`). Subscribing to `useTranslation`
 * re-renders the consumer on a language switch, and the memo rebuilds the copy
 * object for the active language.
 *
 * NOTE: this covers the UI *chrome* (labels, tabs, buttons, orientation copy).
 * AI-generated clinical bodies (guideline synthesis, source shelf) come from the
 * backend and stay English in both locales — see the plan's Phase 2 gate.
 */
export function useAudienceCopy(view: AudienceView): AudienceCopy {
  // react-i18next hands back a fresh `t` on every language change, so depending on
  // the two `t` references (plus the audience) is enough to rebuild on a switch.
  const { t: tHome } = useTranslation("home");
  const { t: tDisease } = useTranslation(view);
  return useMemo(
    () => ({
      home: buildHomeCopy(tHome),
      disease: buildDiseaseCopy(tDisease, view === "parent"),
    }),
    [tHome, tDisease, view],
  );
}

export type { AudienceCopy, DiseaseCopy, HomeCopy } from "./types";
