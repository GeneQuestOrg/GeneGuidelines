import { SettingsView } from "./SettingsView";

export interface SettingsPanelProps {
  isSuperAdmin?: boolean;
}

/** Operator settings — model profiles and integration status (Phase 15). */
export function SettingsPanel({ isSuperAdmin = false }: SettingsPanelProps) {
  return (
    <div className="ops-settings-panel">
      <SettingsView isSuperAdmin={isSuperAdmin} />
    </div>
  );
}
