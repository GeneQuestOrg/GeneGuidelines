import { useEffect, useState } from "react";
import { Badge } from "@gene-guidelines/ui";
import { fetchPipelineSettings, type OperatorSettings } from "../api/client";
import "../styles/ops-settings.css";

function formatTimeout(sec: number): string {
  if (sec >= 3600) return `${Math.round(sec / 3600)} h`;
  if (sec >= 60) return `${Math.round(sec / 60)} min`;
  return `${sec} s`;
}

export function SettingsView() {
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
          Environment-backed configuration (read-only). Update values in the
          server <code>.env</code> and restart the backend.
        </p>
      </header>

      <section className="ops-settings__section">
        <h2>Runtime</h2>
        <dl className="ops-settings__dl">
          <div>
            <dt>Default model profile</dt>
            <dd>
              <code>{settings.defaultModelProfile}</code>
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