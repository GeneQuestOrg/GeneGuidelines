import { describe, expect, it } from "vitest";
import {
  humanizeRunError,
  humanizeTraceMessage,
  parseTraceLine,
} from "./researchRunTrace";

describe("researchRunTrace", () => {
  it("parses SSE JSON trace lines", () => {
    expect(
      parseTraceLine('{"kind":"sys","text":"[SYSTEM] Node pm-1 (Agentic PubMed Retrieval)"}'),
    ).toEqual({
      kind: "sys",
      text: "[SYSTEM] Node pm-1 (Agentic PubMed Retrieval)",
    });
  });

  it("humanizes PubMed telemetry", () => {
    expect(
      humanizeTraceMessage(
        "[SYSTEM] PubMed retrieval telemetry: channel=primary_get, fallback_reason=none, request_count=50, pmids=1818",
      ),
    ).toBe("PubMed search complete — 1818 articles indexed for analysis.");
  });

  it("skips internal boot messages", () => {
    expect(humanizeTraceMessage("[SYSTEM] Import flow_engine: BEFORE.")).toBeNull();
  });

  it("humanizes context length errors", () => {
    const msg = humanizeRunError(
      "ModelHTTPError: maximum context length is 262144 tokens. input_tokens=262145",
    );
    expect(msg).toContain("large PubMed literature set");
    expect(msg).not.toContain("262145");
  });
});
