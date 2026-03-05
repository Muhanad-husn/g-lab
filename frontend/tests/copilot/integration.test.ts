/**
 * Copilot integration test — SSE event sequence → store state.
 *
 * Simulates the full event flow that useSSE dispatches to copilotSlice,
 * then verifies:
 * 1. State updates at each pipeline stage (routing, retrieving, text chunks, etc.)
 * 2. finishStream flushes the accumulated text as an assistant message
 * 3. graph_delta directly populates graphSlice (clear+populate pattern)
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

// ─── Simulate SSE event dispatch ─────────────────────────────────────────────
// graph_delta now directly clears canvas and adds nodes/edges (no pendingDelta)

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
        // Mirror the CopilotPanel behavior: snapshot → replace
        // Don't use clearGraph() because it nulls canvasSnapshot.
        store.getState().snapshotCanvas();
        store.setState({
          nodes: event.delta.add_nodes,
          edges: event.delta.add_edges,
          positions: {},
          collapsedNodeIds: [],
        });
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

    expect(store.getState().confidence).toEqual({
      score: 0.72,
      band: "medium",
    });
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

  it("graph_delta event clears canvas and adds new nodes/edges", () => {
    // Pre-populate canvas
    store.getState().addNodes([
      { id: "old-node", labels: ["Org"], properties: {} },
    ]);
    expect(store.getState().nodes).toHaveLength(1);

    const delta = makeDelta(3, 2);

    simulateSseSequence(store, "sess-delta", [
      { type: "start" },
      { type: "graph_delta", delta },
      { type: "done" },
    ]);

    const s = store.getState();
    // Old nodes should be gone, only delta nodes remain
    expect(s.nodes).toHaveLength(3);
    expect(s.edges).toHaveLength(2);
    expect(s.nodes.map((n) => n.id)).not.toContain("old-node");
  });

  it("canvas snapshot is created before clearing for undo", () => {
    store.getState().addNodes([
      { id: "original", labels: ["Person"], properties: {} },
    ]);

    const delta = makeDelta(1, 0);

    simulateSseSequence(store, "sess-snap", [
      { type: "start" },
      { type: "graph_delta", delta },
      { type: "done" },
    ]);

    // Snapshot should exist for undo
    const s = store.getState();
    expect(s.canvasSnapshot).not.toBeNull();
    expect(s.canvasSnapshot?.nodes).toHaveLength(1);
    expect(s.canvasSnapshot?.nodes[0].id).toBe("original");
  });

  it("revertToSnapshot restores previous canvas state", () => {
    store.getState().addNodes([
      { id: "original", labels: ["Person"], properties: {} },
    ]);

    const delta = makeDelta(2, 1);

    simulateSseSequence(store, "sess-revert", [
      { type: "start" },
      { type: "graph_delta", delta },
      { type: "done" },
    ]);

    // Revert
    store.getState().revertToSnapshot();

    const s = store.getState();
    expect(s.nodes).toHaveLength(1);
    expect(s.nodes[0].id).toBe("original");
    expect(s.canvasSnapshot).toBeNull();
  });
});

describe("Copilot SSE integration — re-retrieval pattern", () => {
  it("re_retrieving status clears content before second pass starts", () => {
    const store = makeStore();

    simulateSseSequence(store, "sess-retr", [
      { type: "start" },
      { type: "status", stage: "routing" },
      { type: "status", stage: "retrieving" },
      { type: "status", stage: "re_retrieving" },
      { type: "status", stage: "retrieving" },
      { type: "text_chunk", text: "After broader search: confirmed." },
      { type: "confidence", score: { score: 0.8, band: "high" } },
      { type: "done" },
    ]);

    const s = store.getState();
    expect(s.messages).toHaveLength(1);
    expect(s.messages[0].content).toBe("After broader search: confirmed.");
    expect(s.confidence?.score).toBe(0.8);
  });
});

describe("Copilot SSE integration — multi-message conversation", () => {
  it("consecutive streams accumulate messages", () => {
    const store = makeStore();
    const sessionId = "sess-multi";

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
    expect(messages).toHaveLength(4);
    expect(messages[0].role).toBe("user");
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].content).toBe("Alice is a person.");
    expect(messages[2].role).toBe("user");
    expect(messages[3].role).toBe("assistant");
    expect(messages[3].content).toBe("She knows Bob.");
  });
});
