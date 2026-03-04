/**
 * Copilot integration test — SSE event sequence → store state → acceptDelta.
 *
 * Simulates the full event flow that useSSE dispatches to copilotSlice,
 * then verifies:
 * 1. State updates at each pipeline stage (routing, retrieving, text chunks, etc.)
 * 2. finishStream flushes the accumulated text as an assistant message
 * 3. acceptDelta applies proposed nodes/edges to graphSlice
 */

import { beforeEach, describe, expect, it } from "vitest";
import { createStore } from "zustand/vanilla";
import { createCopilotSlice, type CopilotSlice } from "@/store/copilotSlice";
import { createGraphSlice, type GraphSlice } from "@/store/graphSlice";
import type {
  CopilotMessage,
  ConfidenceScore,
  EvidenceSource,
  GraphDelta,
} from "@/lib/types";

// ─── Combined store type ───────────────────────────────────────────────────────

type FullStore = CopilotSlice & GraphSlice;

function makeStore() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return createStore<FullStore>()((...a: any[]) => ({
    ...createGraphSlice(...a),
    ...createCopilotSlice(...a),
  }));
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeDelta(nodeCount = 2, edgeCount = 1): GraphDelta {
  return {
    add_nodes: Array.from({ length: nodeCount }, (_, i) => ({
      id: `proposed-node-${i}`,
      labels: ["Person"],
      properties: { name: `Proposed ${i}` },
    })),
    add_edges: Array.from({ length: edgeCount }, (_, i) => ({
      id: `proposed-edge-${i}`,
      type: "KNOWS",
      source: "proposed-node-0",
      target: "proposed-node-1",
      properties: {},
    })),
  };
}

function makeEvidenceSources(): EvidenceSource[] {
  return [
    { type: "graph_path", id: "node-1", content: "Alice → Bob" },
    { type: "graph_path", id: "node-2", content: "Bob → Carol" },
  ];
}

// ─── Simulate SSE event dispatch (mirrors useSSE.ts dispatchEvent) ─────────────
// Instead of calling dispatchEvent directly (not exported), we call the
// corresponding store methods exactly as CopilotPanel does via handlers.

function simulateSseSequence(
  store: ReturnType<typeof makeStore>,
  sessionId: string,
  events: Array<
    | { type: "start" }
    | { type: "status"; stage: string }
    | { type: "text_chunk"; text: string }
    | { type: "evidence"; sources: EvidenceSource[] }
    | { type: "graph_delta"; delta: GraphDelta }
    | { type: "confidence"; score: ConfidenceScore }
    | { type: "done" }
  >,
): void {
  const s = store.getState();

  for (const event of events) {
    switch (event.type) {
      case "start":
        s.startStream();
        break;
      case "status":
        s.setStatus(event.stage);
        break;
      case "text_chunk":
        s.appendTextChunk(event.text);
        break;
      case "evidence":
        s.setEvidence(event.sources);
        break;
      case "graph_delta":
        s.setPendingDelta(event.delta);
        break;
      case "confidence":
        s.setConfidence(event.score);
        break;
      case "done":
        s.finishStream(sessionId);
        break;
    }
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("Copilot SSE integration — happy-path stream sequence", () => {
  let store: ReturnType<typeof makeStore>;

  beforeEach(() => {
    store = makeStore();
  });

  it("initial state has no streaming activity", () => {
    const s = store.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.messages).toHaveLength(0);
    expect(s.pipelineStatus).toBeNull();
    expect(s.confidence).toBeNull();
    expect(s.pendingDelta).toBeNull();
    expect(s.nodes).toHaveLength(0);
  });

  it("full stream sequence produces assistant message", () => {
    const sessionId = "sess-integ-1";

    simulateSseSequence(store, sessionId, [
      { type: "start" },
      { type: "status", stage: "routing" },
      { type: "status", stage: "retrieving" },
      { type: "text_chunk", text: "Alice " },
      { type: "text_chunk", text: "knows Bob." },
      { type: "confidence", score: { score: 0.85, band: "high" } },
      { type: "done" },
    ]);

    const s = store.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingContent).toBe("");
    expect(s.messages).toHaveLength(1);

    const msg = s.messages[0] as CopilotMessage;
    expect(msg.role).toBe("assistant");
    expect(msg.content).toBe("Alice knows Bob.");
    expect(msg.session_id).toBe(sessionId);
  });

  it("pipelineStatus updates correctly across stages", () => {
    const store2 = makeStore();

    store2.getState().startStream();
    expect(store2.getState().pipelineStatus).toBe("starting");

    store2.getState().setStatus("routing");
    expect(store2.getState().pipelineStatus).toBe("routing");

    store2.getState().setStatus("retrieving");
    expect(store2.getState().pipelineStatus).toBe("retrieving");

    store2.getState().finishStream("sess-x");
    expect(store2.getState().pipelineStatus).toBeNull();
  });

  it("confidence is set and persists after stream ends", () => {
    const sessionId = "sess-integ-conf";

    simulateSseSequence(store, sessionId, [
      { type: "start" },
      { type: "text_chunk", text: "Answer." },
      { type: "confidence", score: { score: 0.72, band: "medium" } },
      { type: "done" },
    ]);

    expect(store.getState().confidence).toEqual({ score: 0.72, band: "medium" });
  });

  it("evidence sources are stored during stream", () => {
    const sources = makeEvidenceSources();

    simulateSseSequence(store, "sess-ev", [
      { type: "start" },
      { type: "evidence", sources },
      { type: "done" },
    ]);

    expect(store.getState().evidence).toHaveLength(2);
    expect(store.getState().evidence[0].content).toBe("Alice → Bob");
  });
});

describe("Copilot SSE integration — graph delta flow", () => {
  let store: ReturnType<typeof makeStore>;

  beforeEach(() => {
    store = makeStore();
  });

  it("graph_delta event sets pendingDelta", () => {
    const delta = makeDelta(3, 2);

    simulateSseSequence(store, "sess-delta", [
      { type: "start" },
      { type: "graph_delta", delta },
      { type: "done" },
    ]);

    const s = store.getState();
    expect(s.pendingDelta).not.toBeNull();
    expect(s.pendingDelta?.add_nodes).toHaveLength(3);
    expect(s.pendingDelta?.add_edges).toHaveLength(2);
  });

  it("acceptDelta adds nodes and edges to graphSlice", () => {
    const delta = makeDelta(2, 1);

    store.getState().startStream();
    store.getState().setPendingDelta(delta);
    store.getState().finishStream("sess-accept");

    // Accept the delta
    store.getState().acceptDelta();

    const s = store.getState();
    expect(s.pendingDelta).toBeNull();
    expect(s.nodes).toHaveLength(2);
    expect(s.edges).toHaveLength(1);
    expect(s.nodes.map((n) => n.id)).toContain("proposed-node-0");
    expect(s.nodes.map((n) => n.id)).toContain("proposed-node-1");
  });

  it("acceptDelta deduplicates against existing canvas nodes", () => {
    // Pre-populate canvas with one of the delta nodes
    store.getState().addNodes([
      { id: "proposed-node-0", labels: ["Person"], properties: {} },
    ]);

    const delta = makeDelta(2, 1); // includes proposed-node-0 and proposed-node-1
    store.getState().setPendingDelta(delta);
    store.getState().acceptDelta();

    const s = store.getState();
    // Should have exactly 2 nodes (pre-existing + new, deduped)
    expect(s.nodes).toHaveLength(2);
    expect(s.nodes.map((n) => n.id)).toContain("proposed-node-0");
    expect(s.nodes.map((n) => n.id)).toContain("proposed-node-1");
  });

  it("clearPendingDelta discards delta without modifying graphSlice", () => {
    const delta = makeDelta(2, 1);

    store.getState().setPendingDelta(delta);
    store.getState().clearPendingDelta();

    const s = store.getState();
    expect(s.pendingDelta).toBeNull();
    expect(s.nodes).toHaveLength(0); // graph untouched
    expect(s.edges).toHaveLength(0);
  });

  it("acceptDelta is a no-op when pendingDelta is null", () => {
    store.getState().acceptDelta();

    const s = store.getState();
    expect(s.nodes).toHaveLength(0);
    expect(s.edges).toHaveLength(0);
  });
});

describe("Copilot SSE integration — re-retrieval pattern", () => {
  it("re_retrieving status clears content before second pass starts", () => {
    const store = makeStore();

    // Simulate first pass (low confidence) — this gets discarded by the backend
    // Frontend only sees the status sequence as emitted by the pipeline
    simulateSseSequence(store, "sess-retr", [
      { type: "start" },
      { type: "status", stage: "routing" },
      { type: "status", stage: "retrieving" },
      { type: "status", stage: "re_retrieving" },
      { type: "status", stage: "retrieving" },
      { type: "text_chunk", text: "After broader search: confirmed." },
      { type: "confidence", score: { score: 0.80, band: "high" } },
      { type: "done" },
    ]);

    const s = store.getState();
    expect(s.messages).toHaveLength(1);
    expect(s.messages[0].content).toBe("After broader search: confirmed.");
    expect(s.confidence?.score).toBe(0.80);
  });
});

describe("Copilot SSE integration — multi-message conversation", () => {
  it("consecutive streams accumulate messages", () => {
    const store = makeStore();
    const sessionId = "sess-multi";

    // First query + response
    store.getState().addMessage({
      id: "m1",
      session_id: sessionId,
      role: "user",
      content: "Who is Alice?",
      timestamp: new Date().toISOString(),
    });
    simulateSseSequence(store, sessionId, [
      { type: "start" },
      { type: "text_chunk", text: "Alice is a person." },
      { type: "done" },
    ]);

    // Second query + response
    store.getState().addMessage({
      id: "m3",
      session_id: sessionId,
      role: "user",
      content: "Who does she know?",
      timestamp: new Date().toISOString(),
    });
    simulateSseSequence(store, sessionId, [
      { type: "start" },
      { type: "text_chunk", text: "She knows Bob." },
      { type: "done" },
    ]);

    const messages = store.getState().messages;
    expect(messages).toHaveLength(4); // user, assistant, user, assistant
    expect(messages[0].role).toBe("user");
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].content).toBe("Alice is a person.");
    expect(messages[2].role).toBe("user");
    expect(messages[3].role).toBe("assistant");
    expect(messages[3].content).toBe("She knows Bob.");
  });
});
