import type { ModelProfile } from "../api/client";
import { usePipelineModelSettings } from "./usePipelineModelSettings";

/** Server default from MODEL_PROFILE / single-LLM config in .env. */
export function useDefaultModelProfile(): ModelProfile {
  return usePipelineModelSettings().defaultProfile;
}
