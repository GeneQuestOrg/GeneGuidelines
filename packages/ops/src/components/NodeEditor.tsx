import { useState } from "react";
import type { FlowNode } from "../types";
import { NODE_STYLES, LOOP_POLICIES, EXEC_POLICIES } from "../data/nodeStyles";

/** Payload sent to API on save (prompt + policies + label/description). */
export interface NodeEditorSavePayload {
  prompt: string;
  loop_policy: string;
  execution_policy: string;
  max_retry?: number;
  label?: string;
  description?: string;
  python_source?: string;
  http_url?: string;
  http_method?: string;
  http_headers?: string;
  http_body?: string;
  rag_operation?: string;
  rag_body_json?: string;
  merge_strategy?: string;
  merge_fields?: string;
  merge_key_field?: string;
  integration_operation?: string;
  integration_params_json?: string;
  integration_credentials_json?: string;
  output_schema_key?: string;
  output_schema?: string;
}

interface NodeEditorProps {
  flowKey?: string;
  node: FlowNode | null;
  /** Save version (v1, v2, …) — passed from App so it survives node switches. */
  version?: number;
  onSave?: (payload: NodeEditorSavePayload) => void | Promise<void>;
  onDelete?: () => void | Promise<void>;
}

const labelSt: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: "#64748b",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const inputSt: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  padding: "9px 11px",
  fontSize: 13,
  fontFamily: "inherit",
  outline: "none",
  width: "100%",
};

const OUTPUT_SCHEMA_PRESET_CONFIDENCE = `{
  "confidence": "number",
  "diagnosis": "string",
  "needs_escalation": "boolean"
}`;

/** Legacy API values (auto/approval) — back-compat mapping on read. */
const API_TO_EXEC: Record<string, string> = {
  auto: "Automatic",
  approval: "Requires technician approval",
};

function loopPolicyFromNode(node: { loop_policy?: string } | null): string {
  if (!node?.loop_policy) return LOOP_POLICIES[0];
  return LOOP_POLICIES.includes(node.loop_policy) ? node.loop_policy : LOOP_POLICIES[0];
}
function execPolicyFromNode(node: { execution_policy?: string } | null): string {
  if (!node?.execution_policy) return EXEC_POLICIES[0];
  if (EXEC_POLICIES.includes(node.execution_policy)) return node.execution_policy;
  return API_TO_EXEC[node.execution_policy] ?? EXEC_POLICIES[0];
}

export function NodeEditor({ flowKey, node, version = 1, onSave, onDelete }: NodeEditorProps) {
  const [label, setLabel] = useState(node?.label ?? "");
  const [description, setDescription] = useState(node?.desc ?? "");
  const [prompt, setPrompt] = useState(node?.prompt ?? "");
  const [condition, setCondition] = useState(node?.prompt ?? "");
  const [pythonSource, setPythonSource] = useState(node?.python_source ?? "");
  const [httpUrl, setHttpUrl] = useState(node?.http_url ?? "");
  const [httpMethod, setHttpMethod] = useState(node?.http_method ?? "GET");
  const [httpHeaders, setHttpHeaders] = useState(node?.http_headers ?? "");
  const [httpBody, setHttpBody] = useState(node?.http_body ?? "");
  const [ragOperation, setRagOperation] = useState(node?.rag_operation ?? "similar");
  const [ragBodyJson, setRagBodyJson] = useState(node?.rag_body_json ?? "");
  const [mergeStrategy, setMergeStrategy] = useState(node?.merge_strategy ?? "append");
  const [mergeFields, setMergeFields] = useState(node?.merge_fields ?? "");
  const [mergeKeyField, setMergeKeyField] = useState(node?.merge_key_field ?? "");
  const [integrationOperation, setIntegrationOperation] = useState(node?.integration_operation ?? "");
  const [integrationParamsJson, setIntegrationParamsJson] = useState(node?.integration_params_json ?? "{}");
  const [integrationCredentialsJson, setIntegrationCredentialsJson] = useState(node?.integration_credentials_json ?? "");
  const [outputSchemaKey, setOutputSchemaKey] = useState(node?.output_schema_key ?? "");
  const [outputSchema, setOutputSchema] = useState(node?.output_schema ?? "");
  const [loopPolicy, setLoopPolicy] = useState(loopPolicyFromNode(node));
  const [execPolicy, setExecPolicy] = useState(execPolicyFromNode(node));
  const [maxRetry, setMaxRetry] = useState(node?.max_retry ?? 3);
  const [saved, setSaved] = useState(false);

  if (!node) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          color: "#94a3b8",
          padding: 32,
          textAlign: "center",
        }}
      >
        <div>
          <div style={{ fontSize: 32, marginBottom: 10, opacity: 0.5 }}>←</div>
          <div style={{ fontSize: 14 }}>
            Select a node on the canvas,
            <br />
            to edit it.
          </div>
        </div>
      </div>
    );
  }

  const s = NODE_STYLES[node.type] ?? NODE_STYLES.action;
  const isIntegrationNode = ["slack", "jira", "entra", "email"].includes(node.type);

  const integrationOpsByNode: Record<string, string[]> = {
    slack: ["message", "invite"],
    jira: ["create", "update"],
    entra: ["create", "update", "delete"],
    email: ["send"],
  };

  const opsForCurrentProvider = integrationOpsByNode[node.type] ?? [];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      <div
        style={{
          padding: "18px 20px",
          borderBottom: "1px solid #e2e8f0",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 6,
          }}
        >
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: s.dot,
            }}
          />
          <input
            value={label}
            onChange={(e) => {
              setLabel(e.target.value);
              setSaved(false);
            }}
            placeholder="Node name"
            style={{
              ...inputSt,
              flex: 1,
              fontSize: 16,
              fontWeight: 700,
              border: "none",
              borderBottom: "1px solid transparent",
              padding: "4px 0",
              background: "transparent",
            }}
          />
          {flowKey != null && (
            <span
              style={{
                fontSize: 11,
                color: "#94a3b8",
                fontWeight: 500,
              }}
              title="flow_key · node_id"
            >
              {" "}
              {flowKey} · {node.id}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <span
            style={{
              background: s.bg,
              color: s.color,
              border: `1px solid ${s.border}`,
              borderRadius: 999,
              padding: "2px 10px",
              fontSize: 10.5,
              fontWeight: 700,
              textTransform: "uppercase",
            }}
          >
            {s.label}
          </span>
          <span
            style={{
              background: "#f1f5f9",
              color: "#64748b",
              borderRadius: 999,
              padding: "2px 10px",
              fontSize: 10.5,
              fontWeight: 600,
            }}
          >
            v{version}
          </span>
          {saved && (
            <span
              style={{
                background: "#d1fae5",
                color: "#059669",
                borderRadius: 999,
                padding: "2px 10px",
                fontSize: 10.5,
                fontWeight: 700,
              }}
            >
              SAVED
            </span>
          )}
        </div>
        {s.description ? (
          <p
            style={{
              margin: "10px 0 0",
              fontSize: 12,
              color: "#64748b",
              lineHeight: 1.45,
            }}
          >
            {s.description}
          </p>
        ) : null}
      </div>

      <div
        style={{
          padding: 20,
          overflow: "auto",
          flex: 1,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <label style={labelSt}>Node description</label>
          <textarea
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
              setSaved(false);
            }}
            placeholder="Optional step description"
            rows={2}
            style={{
              ...inputSt,
              resize: "vertical",
              minHeight: 56,
              fontSize: 12.5,
              color: "#64748b",
              lineHeight: 1.5,
              background: "#f8fafc",
            }}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <label style={labelSt}>Action type</label>
          <select style={inputSt} value={s.label} disabled>
            <option>{s.label}</option>
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <label style={labelSt}>Loop Policy</label>
          <select
            style={inputSt}
            value={loopPolicy}
            onChange={(e) => setLoopPolicy(e.target.value)}
          >
            {LOOP_POLICIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <label style={labelSt}>Execution Policy</label>
          <select
            style={inputSt}
            value={execPolicy}
            onChange={(e) => setExecPolicy(e.target.value)}
          >
            {EXEC_POLICIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <label style={labelSt}>Max Retry / Loop Limit</label>
          <input
            type="number"
            min={1}
            max={20}
            value={maxRetry}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!Number.isNaN(v)) setMaxRetry(v);
            }}
            style={inputSt}
          />
        </div>

        {node.type !== "merge" && !isIntegrationNode && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 5,
              flex: 1,
            }}
          >
            <label style={labelSt}>System Prompt / Context</label>
            <textarea
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
                setSaved(false);
              }}
              style={{
                ...inputSt,
                fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                fontSize: 12.5,
                lineHeight: 1.6,
                resize: "vertical",
                minHeight: 200,
                flex: 1,
                background: "#fafbfc",
              }}
            />
          </div>
        )}
        {node.type === "decision" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={labelSt}>Condition (expression)</label>
            <input
              value={condition}
              onChange={(e) => {
                setCondition(e.target.value);
                setSaved(false);
              }}
              placeholder="context['op-2'].confidence >= 0.5"
              style={inputSt}
            />
            <small style={{ color: "#64748b", fontSize: 12 }}>
              Available variables: context['node_id'].field
            </small>
          </div>
        )}
        {(node.type === "prompt" || node.type === "action") && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Output Schema Preset</label>
              <select
                style={inputSt}
                value={outputSchemaKey}
                onChange={(e) => {
                  setOutputSchemaKey(e.target.value);
                  setSaved(false);
                }}
              >
                <option value="">Custom</option>
                <option value="ai_summary">AI Summary</option>
                <option value="diagnostic_result">Diagnostic Result</option>
              </select>
            </div>
            {outputSchemaKey === "" && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <label style={labelSt}>Output Schema (JSON)</label>
                  <button
                    type="button"
                    onClick={() => {
                      setOutputSchema(OUTPUT_SCHEMA_PRESET_CONFIDENCE);
                      setSaved(false);
                    }}
                    style={{
                      background: "#eef2ff",
                      color: "#4338ca",
                      border: "1px solid #c7d2fe",
                      borderRadius: 6,
                      padding: "4px 8px",
                      fontSize: 11.5,
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                    title="Insert preset: confidence, diagnosis, needs_escalation"
                  >
                    Insert preset: confidence/diagnosis
                  </button>
                </div>
                <textarea
                  value={outputSchema}
                  onChange={(e) => {
                    setOutputSchema(e.target.value);
                    setSaved(false);
                  }}
                  rows={8}
                  placeholder='{"issue":"string","work_log_summary":"string"}'
                  style={{
                    ...inputSt,
                    fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                    fontSize: 12.5,
                    resize: "vertical",
                    background: "#f8fafc",
                  }}
                />
              </>
            )}
          </div>
        )}
        {node.type === "merge" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Merge strategy</label>
              <select
                style={inputSt}
                value={mergeStrategy}
                onChange={(e) => {
                  setMergeStrategy(e.target.value);
                  setSaved(false);
                }}
              >
                <option value="append">append</option>
                <option value="zip">zip</option>
                <option value="combine_by_key">combine_by_key</option>
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Merge fields (JSON list)</label>
              <textarea
                value={mergeFields}
                onChange={(e) => {
                  setMergeFields(e.target.value);
                  setSaved(false);
                }}
                placeholder='["items","rows"]'
                rows={6}
                style={{
                  ...inputSt,
                  fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                  fontSize: 12.5,
                  resize: "vertical",
                  background: "#f8fafc",
                }}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Merge key field (for combine_by_key)</label>
              <input
                value={mergeKeyField}
                onChange={(e) => {
                  setMergeKeyField(e.target.value);
                  setSaved(false);
                }}
                placeholder="id"
                style={inputSt}
                disabled={mergeStrategy !== "combine_by_key"}
              />
            </div>
          </div>
        )}
        {isIntegrationNode && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Operation</label>
              <select
                style={inputSt}
                value={integrationOperation}
                onChange={(e) => {
                  setIntegrationOperation(e.target.value);
                  setSaved(false);
                }}
              >
                <option value="" disabled>
                  select…
                </option>
                {opsForCurrentProvider.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Params (JSON)</label>
              <textarea
                value={integrationParamsJson}
                onChange={(e) => {
                  setIntegrationParamsJson(e.target.value);
                  setSaved(false);
                }}
                placeholder='{"channel_id":"...","text":"..."}'
                rows={6}
                style={{
                  ...inputSt,
                  fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                  fontSize: 12.5,
                  resize: "vertical",
                  background: "#f8fafc",
                }}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Credentials (JSON)</label>
              <textarea
                value={integrationCredentialsJson}
                onChange={(e) => {
                  setIntegrationCredentialsJson(e.target.value);
                  setSaved(false);
                }}
                placeholder='{"token":"..."}'
                rows={6}
                style={{
                  ...inputSt,
                  fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                  fontSize: 12.5,
                  resize: "vertical",
                  background: "#f8fafc",
                }}
              />
            </div>
          </div>
        )}
        {node.type === "code" && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 5,
            }}
          >
            <label style={labelSt}>Python Source</label>
            <textarea
              value={pythonSource}
              onChange={(e) => {
                setPythonSource(e.target.value);
                setSaved(false);
              }}
              style={{
                ...inputSt,
                fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                fontSize: 12.5,
                lineHeight: 1.6,
                resize: "vertical",
                minHeight: 220,
                background: "#f8fafc",
              }}
            />
          </div>
        )}
        {node.type === "http_request" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>URL</label>
              <input
                value={httpUrl}
                onChange={(e) => {
                  setHttpUrl(e.target.value);
                  setSaved(false);
                }}
                placeholder="https://… ({{ context.* }})"
                style={inputSt}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>HTTP method</label>
              <select
                style={inputSt}
                value={httpMethod}
                onChange={(e) => {
                  setHttpMethod(e.target.value);
                  setSaved(false);
                }}
              >
                {["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Headers (JSON)</label>
              <textarea
                value={httpHeaders}
                onChange={(e) => {
                  setHttpHeaders(e.target.value);
                  setSaved(false);
                }}
                placeholder='{"Content-Type": "application/json"}'
                rows={4}
                style={{
                  ...inputSt,
                  fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                  fontSize: 12.5,
                  resize: "vertical",
                  background: "#f8fafc",
                }}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Body</label>
              <textarea
                value={httpBody}
                onChange={(e) => {
                  setHttpBody(e.target.value);
                  setSaved(false);
                }}
                rows={5}
                style={{
                  ...inputSt,
                  fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                  fontSize: 12.5,
                  resize: "vertical",
                  background: "#f8fafc",
                }}
              />
            </div>
          </div>
        )}
        {node.type === "rag" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>RAG operation</label>
              <select
                style={inputSt}
                value={ragOperation}
                onChange={(e) => {
                  setRagOperation(e.target.value);
                  setSaved(false);
                }}
              >
                <option value="similar">similar — similar prior runs</option>
                <option value="summary">summary — summarisation</option>
                <option value="suggest_steps">suggest-steps — suggested next steps</option>
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label style={labelSt}>Body (JSON, optional)</label>
              <textarea
                value={ragBodyJson}
                onChange={(e) => {
                  setRagBodyJson(e.target.value);
                  setSaved(false);
                }}
                placeholder='{"text": "{{ context.initial.description }}"}'
                rows={6}
                style={{
                  ...inputSt,
                  fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
                  fontSize: 12.5,
                  resize: "vertical",
                  background: "#f8fafc",
                }}
              />
            </div>
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "nowrap" }}>
          <button
            type="button"
            onClick={async () => {
              setSaved(true);
              await onSave?.({
                prompt: node.type === "decision" ? condition : prompt,
                loop_policy: loopPolicy,
                execution_policy: execPolicy,
                max_retry: maxRetry,
                label,
                description,
                ...(node.type === "code" ? { python_source: pythonSource } : {}),
                ...(node.type === "http_request"
                  ? {
                      http_url: httpUrl,
                      http_method: httpMethod,
                      http_headers: httpHeaders,
                      http_body: httpBody,
                    }
                  : {}),
                ...(node.type === "rag"
                  ? { rag_operation: ragOperation, rag_body_json: ragBodyJson }
                  : {}),
                ...(node.type === "merge"
                  ? {
                      merge_strategy: mergeStrategy,
                      merge_fields: mergeFields,
                      merge_key_field: mergeKeyField,
                    }
                  : {}),
                ...(isIntegrationNode
                  ? {
                      integration_operation: integrationOperation,
                      integration_params_json: integrationParamsJson,
                      integration_credentials_json: integrationCredentialsJson,
                    }
                  : {}),
                ...(node.type === "prompt" || node.type === "action"
                  ? {
                      output_schema_key: outputSchemaKey || undefined,
                      output_schema: outputSchemaKey === "" ? outputSchema : "",
                    }
                  : {}),
              });
            }}
            style={{
              background: "#4f46e5",
              color: "white",
              border: "none",
              borderRadius: 6,
              padding: "9px 18px",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Save Step
          </button>
          {onDelete && (
            <button
              type="button"
              onClick={() => {
                void onDelete();
              }}
              style={{
                background: "#fee2e2",
                color: "#b91c1c",
                border: "1px solid #fecaca",
                borderRadius: 6,
                padding: "9px 18px",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Delete node
            </button>
          )}
          <button
            type="button"
            style={{
              background: "white",
              color: "#1e293b",
              border: "1px solid #e2e8f0",
              borderRadius: 6,
              padding: "9px 18px",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Preview Prompt
          </button>
        </div>
      </div>
    </div>
  );
}
