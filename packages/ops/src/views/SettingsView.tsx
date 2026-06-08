import { useEffect, useState } from "react";
import { Badge } from "@gene-guidelines/ui";
import {
  fetchPipelineSettings,
  updateModelProfileOverride,
  clearModelProfileOverride,
  type OperatorSettings,
} from "../api/client";
import "../styles/ops-settings.css";

function formatTimeout(sec: number): string {
  if (sec >= 3600) return `${Math.round(sec / 3600)} h`;
  if (sec >= 60) return `${Math.round(sec / 60)} min`;
  return `${sec} s`;
}

interface ModelProfileOverrideSectionProps {
  settings: OperatorSettings;
  onSettingsChange: (updated: OperatorSettings) => void;
}

function ModelProfileOverrideSection({
  settings,
  onSettingsChange,
}: ModelProfileOverrideSectionProps) {
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const activeOverride = settings.modelProfileOverride;
  const envDefault = settings.envDefaultModelProfile;

  async function handleSelect(profileId: string) {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateModelProfileOverride(profileId);
      onSettingsChange(updated);
    } catch (e) {
      setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await clearModelProfileOverride();
      onSettingsChange(updated);
    } catch (e) {
      setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ops-settings__section ops-settings__section--override">
      <h2>
        Active model profile{" "}
        <Badge variant="ok">Super-admin</Badge>
      </h2>
      <p className="ops-settings__hint">
        Override the server-default profile for runs that don't specify one explicitly.
        Env default: <code>{envDefault}</code>.
      </p>

      <div className="ops-settings__override-row">
        <select
          className="ops-settings__override-select"
          value={activeOverride ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            if (val) void handleSelect(val);
          }}
          disabled={saving}
          aria-label="Active model profile"
        >
          <option value="" disabled>
            — use env default ({envDefault}) —
          </option>
          {settings.modelProfiles.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.ready}>
              {p.label ?? p.id}
              {!p.ready ? " (missing keys)" : ""}
            </option>
          ))}
        </select>

        {activeOverride ? (
          <button
            className="ops-settings__override-clear"
            onClick={() => void handleClear()}
            disabled={saving}
            aria-label="Clear profile override"
          >
            Reset to env default
          </button>
        ) : null}
      </div>

      {saving ? <p className="ops-settings__hint">Saving…</p> : null}
      {saveError ? (
        <p className="ops-settings__error" role="alert">
          {saveError}
        </p>
      ) : null}

      {activeOverride ? (
        <p className="ops-settings__hint ops-settings__hint--active">
          Active override: <strong>{activeOverride}</strong> — all runs using the
          default profile will use this until cleared.
        </p>
      ) : null}
    </section>
  );
}

export interface SettingsViewProps {
  isSuperAdmin?: boolean;
}

export function SettingsView({ isSuperAdmin = false }: SettingsViewProps) {
  const [settings, setSettings] = useState<OperatorSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void fetchPipelineSettings()
      .then((data) => {
        if (!cancelled) {
          setSettings(data);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="ops-settings__loading">Loading settings…</p>;
  }
  if (error) {
    return (
      <p className="ops-settings__error" role="alert">
        {error}
      </p>
    );
  }
  if (!settings) {
    return <p className="ops-settings__error">No settings returned.</p>;
  }

  const { runtime } = settings;

  return (
    <div className="ops-settings">
      <header className="ops-settings__header">
        <h1>Settings</h1>
        <p>
          Environment-backed configuration. Model profile can be overridden at
          runtime by super-admins.
        </p>
      </header>

      {isSuperAdmin ? (
        <ModelProfileOverrideSection
          settings={settings}
          onSettingsChange={setSettings}
        />
      ) : null}

      <section className="ops-settings__section">
        <h2>Runtime</h2>
        <dl className="ops-settings__dl">
          <div>
            <dt>Default model profile</dt>
            <dd>
              <code>{settings.defaultModelProfile}</code>
              {settings.modelProfileOverride ? (
                <Badge variant="ok">overridden</Badge>
              ) : null}
            </dd>
          </div>
          <div>
            <dt>API key gate</dt>
            <dd>{runtime.apiKeyGateEnabled ? "Enabled" : "Off"}</dd>
          </div>
          <div>
            <dt>Agent run timeout</dt>
            <dd>{formatTimeout(runtime.agentRunTimeoutSec)}</dd>
          </div>
          <div>
            <dt>MCP tools</dt>
            <dd>{runtime.mcpEnabled ? "Enabled" : "Disabled (AGENT_NO_MCP_RUNTIME)"}</dd>
          </div>
          <div>
            <dt>Quality-first hard mode</dt>
            <dd>{runtime.qualityFirstHardMode ? "On" : "Off"}</dd>
          </div>
        </dl>
      </section>

      <section className="ops-settings__section">
        <h2>Model profiles</h2>
        <div className="ops-settings__cards">
          {settings.modelProfiles.map((profile) => (
            <article key={profile.id} className="ops-settings__card">
              <div className="ops-settings__card-head">
                <h3>{profile.label}</h3>
                <Badge variant={profile.ready ? "ok" : "default"}>
                  {profile.ready ? "Ready" : "Missing keys"}
                </Badge>
              </div>
              <ul className="ops-settings__models">
                <li>
                  <span className="ops-settings__model-key">Simple</span>
                  <code>{profile.simpleModel}</code>
                </li>
                <li>
                  <span className="ops-settings__model-key">Agentic</span>
                  <code>{profile.agenticModel}</code>
                </li>
                {profile.overflowModel ? (
                  <li>
                    <span className="ops-settings__model-key">Overflow</span>
                    <code>{profile.overflowModel}</code>
                  </li>
                ) : null}
              </ul>
              {!profile.ready && profile.missingEnvVars.length > 0 ? (
                <p className="ops-settings__hint">
                  Set:{" "}
                  {profile.missingEnvVars.map((v) => (
                    <code key={v}>{v}</code>
                  ))}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="ops-settings__section">
        <h2>Integrations</h2>
        <ul className="ops-settings__integrations">
          {settings.integrations.map((item) => (
            <li key={item.id} className="ops-settings__integration">
              <div className="ops-settings__integration-head">
                <span
                  className={
                    item.configured
                      ? "ops-settings__dot is-ok"
                      : "ops-settings__dot is-missing"
                  }
                  aria-hidden
                />
                <div>
                  <p className="ops-settings__integration-label">{item.label}</p>
                  <p className="ops-settings__integration-env">
                    <code>{item.envVar}</code>
                    {item.optional ? (
                      <span className="ops-settings__optional">optional</span>
                    ) : null}
                  </p>
                </div>
                <Badge variant={item.configured ? "ok" : "default"}>
                  {item.configured ? "Configured" : "Missing"}
                </Badge>
              </div>
              <p className="ops-settings__integration-desc">{item.description}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
