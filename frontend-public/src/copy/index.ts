import type { AudienceView } from "../router/types";
import { doctorCopy } from "./doctor";
import { parentCopy } from "./parent";
import type { AudienceCopy } from "./types";

const COPY_BY_VIEW: Record<AudienceView, AudienceCopy> = {
  parent: parentCopy,
  doctor: doctorCopy,
};

export function getAudienceCopy(view: AudienceView): AudienceCopy {
  return COPY_BY_VIEW[view];
}

export type { AudienceCopy, DiseaseCopy, HomeCopy } from "./types";
