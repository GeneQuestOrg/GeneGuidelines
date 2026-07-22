import { describe, expect, it } from "vitest";
import type { AgentRunPayloadV1 } from "../api/guidelineRun";
import { isQueued, queuedLabel } from "./queuedRun";

function run(partial: Partial<AgentRunPayloadV1>): AgentRunPayloadV1 {
  return {
    contract_version: "v1",
    execution_id: "gl-1",
    ticket_id: 0,
    done: false,
    error: null,
    output: null,
    structured_output: null,
    quality_snapshot: null,
    ai_summary: {},
    diagnostics_entries: [],
    steps_completed_by_ai: [],
    missing_tool_requests: [],
    ...partial,
  };
}

describe("isQueued", () => {
  it("is true for an unfinished run with status queued", () => {
    expect(isQueued(run({ status: "queued" }))).toBe(true);
  });

  it("is false once the run is running", () => {
    expect(isQueued(run({ status: "running" }))).toBe(false);
  });

  it("is false when done even if status lingers as queued", () => {
    expect(isQueued(run({ status: "queued", done: true }))).toBe(false);
  });

  it("is false for a null run", () => {
    expect(isQueued(null)).toBe(false);
  });
});

describe("queuedLabel", () => {
  it("includes the position when known", () => {
    expect(queuedLabel(3)).toEqual({
      key: "queuedRun.queuedWithPosition",
      params: { position: 3 },
    });
  });

  it("omits the position when null or non-positive", () => {
    expect(queuedLabel(null)).toEqual({ key: "queuedRun.queuedNoPosition" });
    expect(queuedLabel(0)).toEqual({ key: "queuedRun.queuedNoPosition" });
  });
});
