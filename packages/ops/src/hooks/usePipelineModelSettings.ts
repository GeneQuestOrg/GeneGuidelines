import { useEffect, useState } from "react";
import {
  fetchPipelineSettings,
  type ModelProfile,
} from "../api/client";

const ALL_PROFILES: ModelProfile[] = ["production", "openrouter", "test", "vllm"];

export interface PipelineModelSettings {
  defaultProfile: ModelProfile;
  profileOptions: ModelProfile[];
  singleLlmMode: boolean;
  singleLlmModel: string | null;
}

const FALLBACK: PipelineModelSettings = {
  defaultProfile: "vllm",
  profileOptions: ALL_PROFILES,
  singleLlmMode: false,
  singleLlmModel: null,
};

/** Server-backed default profile and whether the UI should hide multi-provider choice. */
export function usePipelineModelSettings(): PipelineModelSettings {
  const [settings, setSettings] = useState<PipelineModelSettings>(FALLBACK);

  useEffect(() => {
    void fetchPipelineSettings()
      .then((s) => {
        const options: ModelProfile[] = s.singleLlmMode
          ? ["vllm"]
          : (s.modelProfiles.map((p) => p.id) as ModelProfile[]);
        setSettings({
          defaultProfile: s.defaultModelProfile as ModelProfile,
          profileOptions: options.length > 0 ? options : ALL_PROFILES,
          singleLlmMode: Boolean(s.singleLlmMode),
          singleLlmModel: s.singleLlmModel ?? null,
        });
      })
      .catch(() => {
        setSettings(FALLBACK);
      });
  }, []);

  return settings;
}
